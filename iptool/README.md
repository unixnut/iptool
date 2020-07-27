Introduction
============
`iptool` is designed to list interface info including IP addresses in a
non-crazy format yet with as much useful info as possible.  In effect,
it's a more sensible replacement for `ip addr show` that skips
information that you probably don't want (e.g. qdisc); also elides the
IPv4 address alias if it's the same as the interface name.  It uses a
much more concise way of describing the interface state; see below.  It
also gives more detail about the type of the interface and shows the
parent of VLAN virtual interfaces.

By default only the "essential" information is shown; use verbose flags
to get more.  (Not currently implemented.)

In future it will also show bridging info.


Invocation
==========

  - `iptool list` (default) -- sorts by interface name (`-s` for state or `-i` for ID)
  - `iptool addrs` -- sorts by address
  - `iptool status` -- shows Friendly state of interface(s)
  - `iptool state` -- alias for `iptool status`


Interface states
================

There are two ways of tracking network interface state.  They are
confusing.  (I call these "Basic state flags" and "Enhanced state"; the
latter is also known as `operstate`.)

I have come up with an abstraction covering both states called "Friendly
state" that encapsulates the actual state of the interface in an easily
comprehensible way.
(Enhanced state takes precedence unless marked as N/A.
Basic state flags columns assumes IFF_UP set (unless stated otherwise)
in addition to other conditions.)

( Basic state flags    | Enhanced state         | Friendly state | Notes             |
|----------------------|------------------------|----------------|-------------------|
| IFF_UP not set       | N/A	                | disabled       | Manual override   |
|                      | IF_OPER_UP             | up             |                   |
|                      | IF_OPER_NOTPRESENT     | not-present    |                   |
|                      | IF_OPER_DOWN           | down           |                   |
|                      | IF_OPER_LOWERLAYERDOWN | waiting        |                   |
|                      | IF_OPER_TESTING        | testing        |                   |
|                      | IF_OPER_DORMANT        | dormant        |                   |
| IFF_LOWER_UP set     | IF_OPER_UNKNOWN        | up             | No enhanced state |
| IFF_LOWER_UP not set | IF_OPER_UNKNOWN        | down           | No enhanced state |


TO-DO
=====

  - MTU
  - By default, elide link-local addresses, interface IDs (and VLAN parent IDs),
    MTU and MAC addresses
  - `-a` shows global addresses only
  - `-v` show MAC addresses and MTU
  - `-vv` also show interface IDs, address flags and link-local addresses
  - `-o` only shows enabled interfaces
  - `-t` shows multiple addresses per line (link scope at start)
  - Sort addresses by octet/word (":" comes first)
  - Make interface name bold and use colours for Friendly state
  - Colorise as per iproute2
  - Show % suffixes for link-local addresses
  - Make NetlinkSocket::process_messages() use NetlinkSocket::process_rta_chain() 
  - Show bridging info for interfaces
  - Sub-commands for showing bridge and route info
  - decode VLAN flags: 00c8
  - decode unknown rtattr of type 3 (len: 4) -- found on a bridge interface
  - Use "socket(PF_INET, SOCK_DGRAM, IPPROTO_IP)" and SIOCETHTOOL to get link speed
