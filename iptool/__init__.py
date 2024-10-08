'''Description: iptool is designed to list interface info including IP addresses
  It does so in a non-crazy format yet with as much useful info as possible.
  In effect, it's a more sensible replacement for "ip addr show" that skips
  information that you probably don't want (e.g. qdisc); also elides the IPv4
  address alias if it's the same as the interface name.
  
Usage:
  iptool [ -sigc ] [ <interface> ]
Options:
  -s  --state-sort   Sorts by interface state, then name
  -i  --id-sort      Sorts by interface ID
  -g  --no-grouping  Don't sort by interface type (loopback, other, tunnel)
  -vv                Show link-local addresses
  -c  --compact      Don't show a blank line between interfaces
'''



__version__ = "1.1.0"

import sys
import getopt
import socket
import os
import ctypes
import binascii
import types

import cpylmnl.linux.netlinkh as netlink
import cpylmnl.linux.rtnetlinkh as rtnl
import cpylmnl.linux.if_addrh as if_addr

from . import iplist
from . import families
from .globals import params


self="iptool"
allowed_options='hdsigcv'
allowed_long_options=['help', 'state-sort', 'id-sort', 'no-grouping', 'compact', 'verbose']



# *** CLASSES ***

class NetlinkSocket(object):
    def __init__(self, proto):
        self.sock = socket.socket(socket.AF_NETLINK, socket.SOCK_DGRAM, proto)
        self.sock.bind((0,0))

        self.hdr = netlink.Nlmsghdr()
        self.hdr.nlmsg_len = -1
        self.hdr.nlmsg_type = -1
        self.hdr.nlmsg_seq = 0
        self.hdr.nlmsg_pid = os.getpid()


    def send_msg(self, msg_type, payload):
        payload_len = payload.csize()

        self.hdr.nlmsg_seq += 1
        self.hdr.nlmsg_len = netlink.NLMSG_ALIGN(netlink.NLMSG_LENGTH(payload_len))
        self.hdr.nlmsg_type = msg_type
        # 
        if type(payload) is rtnl.Rtgenmsg:
            self.hdr.nlmsg_flags = netlink.NLM_F_REQUEST | netlink.NLM_F_DUMP
        else:
            self.hdr.nlmsg_flags = netlink.NLM_F_REQUEST | netlink.NLM_F_MATCH

        # start with a zero-filled buffer padded appropriately
        buf = ctypes.create_string_buffer(self.hdr.nlmsg_len)
        ctypes.memmove(buf, ctypes.addressof(self.hdr), netlink.NLMSG_HDRLEN)
        ctypes.memmove(ctypes.addressof(buf) + netlink.NLMSG_HDRLEN, ctypes.addressof(payload), payload_len)

        ## print("Sending", len(buf.raw), "bytes:")
        ## print("  ", binascii.hexlify(buf.raw))
        self.sock.send(buf.raw)

        self.msg_type = msg_type


    def recv_msg(self, maxsize):
        rdata = self.sock.recv(maxsize)
        ## print(len(rdata), "bytes received!")
        return ctypes.create_string_buffer(rdata, len(rdata))


    def transact(self, msg_type, payload):
        """Sends a request and receives datagrams, returning each one as an
        element (containing a message list) of an array."""
        self.send_msg(msg_type, payload)
        buf = self.recv_msg(8192)
        msgs = [buf]

        hdr = netlink.Nlmsghdr.from_pointer(buf)
        if hdr.nlmsg_flags == netlink.NLM_F_MULTI:
            while hdr.nlmsg_type != netlink.NLMSG_DONE:
                ## print("... message type =", hdr.nlmsg_type)
                buf = self.recv_msg(8192)
                msgs.append(buf)
                hdr = netlink.Nlmsghdr.from_pointer(buf)

        return msgs


    def process_messages(self, buf, fn, *args):
        """Calls fn on each message in the buffer, passing a pointer to the
        "sub-buffer", i.e. the data after the Nlmsghdr."""

        return_values = []

        if len(buf) > 0:
            # store this on the stack because the object's property might
            # change due to recursive processing
            expected_type = self.msg_type

            # buffer contains messages, each with their own Nlmsghdr
            # ...then comes a sub-header (e.g. Ifinfomsg) followed by a number of Rtattr

            buf_ptr = ctypes.cast(buf, ctypes.c_void_p)
            # ptr walks through the buffer, pointing at each message
            ptr = buf_ptr
            while ptr.value - buf_ptr.value < len(buf):
                ## print("Processed %d of %d bytes" % (ptr.value - buf_ptr.value, len(buf)))
                # Map a header pointer to the start of the message
                hdr = netlink.Nlmsghdr.from_pointer(ptr)
                ## print("internal message len = ", hdr.nlmsg_len)
                ## print("message type = %d [%d]" % (hdr.nlmsg_type, hdr.nlmsg_seq))
                if hdr.nlmsg_type != netlink.NLMSG_DONE:
                    # Compare the RTNL_FAMILY_* values of the request and response
                    ## print("fam = %d (expected %d)" % (rtnl.RTM_FAM(hdr.nlmsg_type), rtnl.RTM_FAM(expected_type)))
                    if rtnl.RTM_FAM(hdr.nlmsg_type) != rtnl.RTM_FAM(expected_type):
                        if rtnl.RTM_FAM(expected_type) == families.RTNL_FAMILY_ADDR and \
                           rtnl.RTM_FAM(hdr.nlmsg_type) == families.RTNL_FAMILY_LINK:
                            print("extra link message")
                        else:
                            print("bad type! (%s)" % hdr.nlmsg_type, file=sys.stderr)
                            sys.exit(3)
                    else:
                        # Process the message
                        # Map a message pointer into the buffer, starting after the header
                        # Due to the pointer type created, effectively a sub-buffer is passed
                        return_values.append(
                          fn(self, ctypes.cast(netlink.NLMSG_DATA(hdr), 
                                               ctypes.POINTER((ctypes.c_ubyte * netlink.NLMSG_PAYLOAD(hdr, 0)))), *args))

                # Advance the pointer to the next message
                ptr = ctypes.c_void_p(ptr.value + hdr.nlmsg_len)

        return return_values


    def process_rta_chain(self, data, table, meta = None):
        """Deals with a sequence of rtattr structures.
        @param data     A ctypes array containing the structures
        @param table    An associative array mapping rta_type IDs to one of the following:
                          - a function, i.e. fn(id, data, meta) that returns a tuple consisting of a property name and a value
                          - OR a tuple consisting of a property name and a similar table showing how to process nesting rtattr structures
        @param meta     Optional information passed down the call tree
        @return         An associative array of property names mapping to info values
        """

        return_values = {}

        # Find the first Rtattr
        bytes_remaining = len(data.contents)
        attr = rtnl.Rtattr.from_address(ctypes.addressof(data.contents))

        while bytes_remaining > 0:
            ## print(attr.rta_type)
            if attr.rta_type in table:
                if type(table[attr.rta_type]) == types.FunctionType:
                    label, info = table[attr.rta_type](attr.rta_type, rtnl.RTA_DATA(attr), meta)
                    return_values[label] = info
                else:
                    label, subtable = table[attr.rta_type]
                    return_values[label] = self.process_rta_chain(rtnl.RTA_DATA(attr), subtable, meta)
            else:
                # use this tables's default handler function, if any
                if if_addr.IFA_UNSPEC in table:
                    label, info = table[if_addr.IFA_UNSPEC](attr.rta_type, rtnl.RTA_DATA(attr), meta)
                    return_values[label] = info

            # advance to the next Rtattr
            attr, bytes_remaining = rtnl.RTA_NEXT(attr, bytes_remaining)

        return return_values


# *** FUNCTIONS ***
def show_help(dest=sys.stdout):
    print(__doc__, end='', file=dest)


def report_error(*msg):
    print(self + ": Error:", msg, file=sys.stderr)


def report_warning(*msg):
    print(self + ": Warning:", msg, file=sys.stderr)


def report_notice(*msg):
    print(self + ": Notice:", msg, file=sys.stderr)



# *** MAINLINE ***
# See __main__.py
# (Invoke with "python -m shepherd" under Python 2.7+, otherwise
# "python -m shepherd.__main__")

def main(argv):
    """Acts like main() in a C program.  Return value is used as program exit code."""

    global params

    # == Command-line parsing ==
    # -- defaults --
    debug = 0
    params['blank-lines'] = True
    params['verbose'] = 0

    # -- option handling --
    try:
        optlist, args = getopt.getopt(argv[1:], allowed_options, allowed_long_options)
    except getopt.GetoptError as e:
        report_error(e)
        return 1

    for option, opt_arg in optlist:
        if option == "-s" or option == "--state-sort":
            params['state-sort'] = True
        if option == "-i" or option == "--id-sort":
            params['id-sort'] = True
        if option == "-g" or option == "--no-grouping":
            params['no-grouping'] = True
        if option == "-c" or option == "--compact":
            params['blank-lines'] = False
        elif option == "-v" or option == "--verbose":
            params['verbose'] += 1
        elif option == "-d":
            debug += 1
        elif option == "-h" or option == "--help":
            show_help()
            return 0

    # -- argument checking --
    ## if len(args) not in (2, 3):
    ##     report_error("Invalid command-line parameters.")
    ##     show_help(sys.stderr)
    ##     return 1

    s = NetlinkSocket(socket.NETLINK_ROUTE)
    ## iplist.get_addr(s)
    interfaces = iplist.get_interfaces(s)
    addrs_by_interface = iplist.get_addrs(s, interfaces)

    if len(args) == 1:
        matching_ids = [i for i in interfaces if interfaces[i].info['name'] == args[0]]
        matching_interfaces = {}
        for i in matching_ids:
            matching_interfaces[i] = interfaces[i]
        iplist.show_links(matching_interfaces, addrs_by_interface)
    else:
        iplist.show_links(interfaces, addrs_by_interface)

    ## print(addrs_by_interface.keys())
