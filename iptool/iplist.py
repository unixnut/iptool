import sys
import socket
import ctypes
import binascii

import cpylmnl.linux.netlinkh as netlink
import cpylmnl.linux.rtnetlinkh as rtnl
import cpylmnl.linux.if_linkh as if_link
import cpylmnl.linux.if_addrh as if_addr
import cpylmnl.linux.ifh

from .interface import Interface
from . import util
from .globals import params


def pointer_add(p, i):
    """Takes any pointer and returns a void pointer with an amount in bytes
    (may be negative) added"""
    return ctypes.c_void_p(ctypes.cast(p, ctypes.c_void_p).value + i)


def get_interfaces(s):
    payload = rtnl.Rtgenmsg()
    payload.rtgen_family = socket.AF_UNSPEC    # socket.AF_INET

    return_values = {}
    for buf in s.transact(rtnl.RTM_GETLINK, payload):
        for i in s.process_messages(buf, get_link_info):
            return_values[i.id] = i

    return return_values


def show_links(interfaces, addrs_by_interface):
    count = 0
    for i in sorted(interfaces.values()):
        count += 1
        if params['blank-lines'] and count > 1:
            print()
        i.show_link_info(addrs_by_interface)


# @param message    A pointer to an array of the size of the sub-buffer
# @param family     Which INET family to use, or None for all
def get_link_info(s, chunk):
    return Interface(s, chunk)


def get_addrs(s, interfaces, family = None):
    """Match semantics only work for address family, so do a dump and return an
    associative array (indexed by interface ID) of arrays of address info (each
    element being an associative array)."""

    if family is None:
        payload = rtnl.Rtgenmsg()
        payload.rtgen_family = socket.AF_UNSPEC    # socket.AF_INET
    else:
        payload = if_addr.Ifaddrmsg()
        ctypes.memset(ctypes.addressof(payload), 0, ctypes.sizeof(payload))
        payload.ifa_family = family
        ## payload.ifa_family = socket.AF_INET
        ## payload.ifa_flags = 
        ## payload.ifa_index = i

    d = {}
    for buf in s.transact(rtnl.RTM_GETADDR, payload):
        # Get all the addresses and then store each one in a list belonging to
        # its respective interface ID
        for info in s.process_messages(buf, get_addr_info, interfaces):
            if info['interface'] in d:
                d[info['interface']].append(info)
            else:
                d[info['interface']] = [info]

    return d


# @param chunk    A pointer to an array of the size of the sub-buffer
def get_addr_info(s, chunk, interfaces):
    ## print("sub-buffer length:", len(chunk.contents))
    ifaddrmsg = if_addr.Ifaddrmsg.from_pointer(chunk)
    interface_info = interfaces[ifaddrmsg.ifa_index]

    # Find the first Rtattr
    offset = netlink.NLMSG_ALIGN(ctypes.sizeof(ifaddrmsg))
    bytes_remaining = len(chunk.contents) - offset
    ## attr = rtnl.Rtattr.from_address(ctypes.addressof(chunk.contents) + offset)
    attr = if_addr.IFA_RTA(chunk.contents)

    # Process attributes to find name, hardware address, etc.
    info = {'interface': ifaddrmsg.ifa_index,
            'prefix': ifaddrmsg.ifa_prefixlen,
            'scope': ifaddrmsg.ifa_scope, 'flags': ifaddrmsg.ifa_flags}
    unprocessed = []
    while bytes_remaining > 0:
        if attr.rta_type == if_addr.IFA_LABEL:
            info['name'] = ctypes.cast(rtnl.RTA_DATA(attr), ctypes.c_char_p).value.decode('ascii')
        elif attr.rta_type == if_addr.IFA_ADDRESS or attr.rta_type == if_addr.IFA_LOCAL:
            addr_len = rtnl.RTA_PAYLOAD(attr)
            addr_ptr = ctypes.cast(rtnl.RTA_DATA(attr),
                                   ctypes.POINTER((ctypes.c_ubyte * addr_len)))
            addr_bytes = (ctypes.c_char * addr_len).from_buffer(addr_ptr.contents).raw
            addr_str = socket.inet_ntop(ifaddrmsg.ifa_family, addr_bytes)
            if interface_info.flags & cpylmnl.linux.ifh.IFF_POINTOPOINT and \
               attr.rta_type == if_addr.IFA_ADDRESS:
                info['remote_addr'] = addr_str
            else:
                info['addr'] = addr_str
        elif attr.rta_type == if_addr.IFA_FLAGS:
            # This overrides ifaddrmsg.ifa_flags
            ## if 'flags' in info:
            ##     print("orig =", info['flags'])
            info['flags'] = (ctypes.cast(rtnl.RTA_DATA(attr),
                                         ctypes.POINTER(ctypes.c_uint))).contents.value
            ## print("new =", info['flags'])
        else:
            unprocessed.append(attr.rta_type)
            ## info[attr.rta_type] = 
            ## print(binascii.hexlify(ctypes.cast(rtnl.RTA_DATA(attr), ctypes.POINTER(ctypes.c_char))[0:rtnl.RTA_PAYLOAD(attr)]))

        attr, bytes_remaining = rtnl.RTA_NEXT(attr, bytes_remaining)

    return info

