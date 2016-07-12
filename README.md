iptool package
~~~~~~~~~~~~~~

Uses `netlink` sockets just like `iproute2`.  Partial replacement for the `ip`
and `brctl` commands; the modules in this package show info only.

Contains two modules:

  - [iptool](iptool): Lists interface info including IP addresses in a non-crazy format
  - [cpylmnl](cpylmnl): Submodle (https://github.com/unixnut/cpylmnl) forked from [chamaken/cpylmnl](https://github.com/chamaken/cpylmnl) in order to fix bugs
