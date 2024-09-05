import ctypes
import binascii

import cpylmnl.linux.rtnetlinkh as rtnl
import cpylmnl.linux.ifh
import cpylmnl.linux.if_linkh as if_link
import cpylmnl.linux.if_addrh as if_addr


link_types = { 1: "Ethernet", 772: "loopback", 0xFFFE: "other" }
addr_scopes = { rtnl.RT_SCOPE_UNIVERSE: "global",
                rtnl.RT_SCOPE_SITE:     "site",
                rtnl.RT_SCOPE_LINK:     "link",
                rtnl.RT_SCOPE_HOST:     "host",
                rtnl.RT_SCOPE_NOWHERE:  "nowhere" }

operstates = { cpylmnl.linux.ifh.IF_OPER_UP: "up",
               cpylmnl.linux.ifh.IF_OPER_NOTPRESENT: "not-present",
               cpylmnl.linux.ifh.IF_OPER_DOWN: "down",
               cpylmnl.linux.ifh.IF_OPER_LOWERLAYERDOWN: "waiting",
               cpylmnl.linux.ifh.IF_OPER_TESTING: "testing",
               cpylmnl.linux.ifh.IF_OPER_DORMANT: "dormant" }



def default_rtattr_handler(id, data, meta):
    return "unknown", "unknown rtattr of type %d (len: %d)" % (id, ctypes.sizeof(data.contents))

default_rtattr_map = { if_addr.IFA_UNSPEC: default_rtattr_handler }


def vlan_rtattr_handler(id, data, meta):
    ## print ctypes.sizeof(data.contents)
    if id == if_link.IFLA_VLAN_ID:
        return 'vlan_id', (ctypes.cast(data, ctypes.POINTER(ctypes.c_short))).contents.value
    elif id == if_link.IFLA_VLAN_FLAGS:
        vlan_flags = (ctypes.cast(data, ctypes.POINTER(if_link.IflaVlanFlags))).contents
        return 'vlan_flags', vlan_flags.flags

link_data_rtattr_map = { if_link.IFLA_VLAN_ID: vlan_rtattr_handler,
                         if_link.IFLA_VLAN_FLAGS: vlan_rtattr_handler,
                         if_addr.IFA_UNSPEC: default_rtattr_handler }

def link_kind_rtattr_handler(id, data, meta):
    return 'kind', ctypes.cast(data, ctypes.c_char_p).value.decode('ascii')

link_info_rtattr_map = { if_link.IFLA_INFO_KIND: link_kind_rtattr_handler,
                         if_link.IFLA_INFO_DATA: ('data', link_data_rtattr_map),
                         if_addr.IFA_UNSPEC: default_rtattr_handler }

def decode_link_type(type):
    return link_types.get(type, "unknown")


def decode_mac_addr(arr):
    return ':'.join(['%02x' % n for n in arr])


def decode_scope(scope):
    return addr_scopes[scope]


def decode_link_state(operstate, flags):
    # Note that IF_OPER_LOWERLAYERDOWN and IFF_LOWER_UP cover different areas
    # See https://www.kernel.org/doc/Documentation/networking/operstates.txt
    ## return '%d [%04x]' % (operstate, flags)
    if not flags & cpylmnl.linux.ifh.IFF_UP:
        return "disabled"
    elif operstate != cpylmnl.linux.ifh.IF_OPER_UNKNOWN:
        return operstates[operstate]
    else:
        if flags & cpylmnl.linux.ifh.IFF_LOWER_UP:
            return operstates[cpylmnl.linux.ifh.IF_OPER_UP]
        else:
            return operstates[cpylmnl.linux.ifh.IF_OPER_DOWN]


def add_extra(s, l):
    """Takes a string, and if there are any items in the list, appends parentheses
    to the end, containing the list items separated by semicolons."""
    if len(l) > 0:
        return "%s (%s)" % (s, "; ".join(l))
    else:
        return s
