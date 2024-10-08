import socket
import ctypes
import functools

import cpylmnl.linux.netlinkh as netlink
import cpylmnl.linux.rtnetlinkh as rtnl
import cpylmnl.linux.ifh
import cpylmnl.linux.if_linkh as if_link
import cpylmnl.linux.if_addrh as if_addr

from . import util
from .globals import params


class Interface(object):
    def __lt__(a, b):
        """
        Allows sorting of interfaces by name.  Forces the loopback interface to
        be first in the sequence.
        """

        ## if a.info['name'] == "lo":
        if not params['no-grouping'] and \
           a.info['flags'] & cpylmnl.linux.ifh.IFF_LOOPBACK != \
           b.info['flags'] & cpylmnl.linux.ifh.IFF_LOOPBACK:
            # The maths works on the bit in each flags word
            return (a.info['flags'] & cpylmnl.linux.ifh.IFF_LOOPBACK) > 0
        elif not params['no-grouping'] and \
             a.is_tun() != b.is_tun():
            return b.is_tun()   # Tunnel interfaces come later
        elif params['state-sort'] and a.get_state() != b.get_state():
            return b.get_state() < a.get_state()
        elif params['id-sort']:
            return a.info['id'] < b.info['id']
        else:
            return a.info['name'] < b.info['name']


    ## @classmethod
    ## def get_sort_key_fn(cls):
    ##     return functools.cmp_to_key(cls.cmp)


    # Warning: don't store ifinfomsg header or data because the buffer it's in
    # could be garbage collected
    def __init__(self, s, chunk):
        ## print("sub-buffer length:", len(chunk.contents))
        ifinfomsg = rtnl.Ifinfomsg.from_pointer(chunk)
        ## print(binascii.hexlify(ctypes.cast(chunk, ctypes.POINTER(ctypes.c_char))[0:16]))
        ## print("%d (%d)" % (ifinfomsg.ifi_index, ifinfomsg.ifi_type))

        # Find the first Rtattr
        offset = netlink.NLMSG_ALIGN(ctypes.sizeof(ifinfomsg))
        bytes_remaining = len(chunk.contents) - offset
        ## print(bytes_remaining, "...")
        ## attr = rtnl.Rtattr.from_address(ctypes.addressof(chunk.contents) + offset)
        attr = if_link.IFLA_RTA(chunk.contents)

        # Process attributes to find name, hardware address, etc.
        self.info = {'link_type': util.decode_link_type(ifinfomsg.ifi_type),
                     'id': ifinfomsg.ifi_index,
                     'flags': ifinfomsg.ifi_flags, 'state': cpylmnl.linux.ifh.IF_OPER_UNKNOWN }
        unprocessed = []
        while bytes_remaining > 0:
            data_ptr = rtnl.RTA_DATA(attr)
            ## print("type:", attr.rta_type)
            if attr.rta_type == if_link.IFLA_IFNAME:
                self.info['name'] = ctypes.cast(data_ptr, ctypes.c_char_p).value.decode('ascii')
            elif attr.rta_type == if_link.IFLA_LINK:
                # Only for VLANs, etc.; this is the ID of the real interface
                self.info['parent_link'] = (ctypes.cast(data_ptr, ctypes.POINTER(ctypes.c_int))).contents.value
            elif attr.rta_type == if_link.IFLA_ADDRESS:
                # This should also handle longer MAC addrs
                addr_len = rtnl.RTA_PAYLOAD(attr)
                mac_bytes = ctypes.cast(data_ptr, ctypes.POINTER((ctypes.c_ubyte * addr_len))).contents
                self.info['hwaddr'] = util.decode_mac_addr(mac_bytes)
            elif attr.rta_type == if_link.IFLA_OPERSTATE:
                # See https://www.kernel.org/doc/Documentation/networking/operstates.txt
                self.info['state' ] = (ctypes.cast(data_ptr, ctypes.POINTER(ctypes.c_ubyte))).contents.value
            elif attr.rta_type == if_link.IFLA_MTU:
                self.info['mtu' ] = (ctypes.cast(data_ptr, ctypes.POINTER(ctypes.c_uint))).contents.value
            elif attr.rta_type == if_link.IFLA_LINKINFO:
                ## self.info['details'] = rtnl.RTA_PAYLOAD(attr)
                self.info['link_info'] = s.process_rta_chain(data_ptr, util.link_info_rtattr_map, self)
            else:
                unprocessed.append(attr.rta_type)
            # IFLA_GROUP

            # Post-process the link_type if we have better information
            if self.info['link_type'] == "other" and \
               'link_info' in self.info and 'kind' in self.info['link_info']:
                self.info['link_type'] = self.info['link_info']['kind']
                del self.info['link_info']['kind']

            # advance to the next Rtattr
            attr, bytes_remaining = rtnl.RTA_NEXT(attr, bytes_remaining)

        ## print("   ", unprocessed)


    def show_link_info(self, addrs):
        t = self.info['link_type']
        extra_info = [self.get_state()]
        extra_info.append("ID: %d" % self.info['id'])
        if 'hwaddr' in self.info and t != 'loopback':
            extra_info.append("MAC addr: " + self.info['hwaddr'])
        if 'details' in self.info:
            extra_info.append("%d bytes of link info" % self.info['details'])
        if 'link_info' in self.info:
            if 'kind' in self.info['link_info']:
                # treat it as a subtype if the actual link type wasn't "other"
                ## extra_info.append("sub-type: " + self.info['link_info']['kind'])
                t = "%s (%s)" % (t, self.info['link_info']['kind'])
            if 'data' in self.info['link_info']:
                if 'vlan_id' in self.info['link_info']['data']:
                    extra_info.append("VLAN ID: %d" % self.info['link_info']['data']['vlan_id'])
                if 'vlan_flags' in self.info['link_info']['data']:
                    extra_info.append("VLAN flags: %04x" % self.info['link_info']['data']['vlan_flags'])
                if 'unknown' in self.info['link_info']['data']:
                    extra_info.append(self.info['link_info']['data']['unknown'])

        if 'parent_link' in self.info:
            print("%s [%d] (%s; %s):" % (self.info['name'], self.info['parent_link'],
                                         t, "; ".join(extra_info)))
        else:
            print("%s (%s; %s):" % (self.info['name'], t, "; ".join(extra_info)))

        self.show_addrs(self.info['id'], addrs, params['verbose'] >= 2)


    def get_state(self):
        return util.decode_link_state(self.info['state'], self.info['flags'])


    def is_tun(self):
        return self.info['link_type'] == "tun" or \
                'link_info' in self.info and 'kind' in self.info['link_info'] and self.info['link_info']['kind'] == "tun"


    def show_addrs(self, i, addrs, include_link_local = True):
        if i in addrs:
            ## TO-DO: sort
            if_addrs = [addr for addr in addrs[i] if addr['scope'] != rtnl.RT_SCOPE_LINK or include_link_local]
        else:
            if_addrs = []

        if if_addrs:
            for addr in if_addrs:
                self.show_addr_info(addr)
        else:
            print("    no addresses")


    def show_addr_info(self, addr_info):
        extra_info = [util.decode_scope(addr_info['scope'])]
        if extra_info == ['global']:
            extra_info = []
        ## if self.info['flags'] & cpylmnl.linux.ifh.IFF_POINTOPOINT:
        if 'remote_addr' in addr_info:
            extra_info.append("remote: %s" % addr_info['remote_addr'])
        # Only show the flags if they're not just IFA_F_PERMANENT
        ## addr_info['flags']
        if 'name' in addr_info and addr_info['name'] != self.info['name']:
            print(util.add_extra("    %s: %s/%d" % (addr_info['name'], addr_info['addr'], addr_info['prefix']),
                                 extra_info))
        else:
            ## print addr_info
            if 'addr' in addr_info:
                print(util.add_extra("    %s/%d" % (addr_info['addr'], addr_info['prefix']),
                                     extra_info))
            else:
                print(util.add_extra("    no local address",
                                     extra_info))
            ## print "    %s/%d (%d [%04x])" % (addr_info['addr'], addr_info['prefix'], addr_info['scope'], addr_info['flags'])


    def __getattr__(self, a):
        return self.info[a]
