iptool package
~~~~~~~~~~~~~~

Uses `netlink` sockets just like `iproute2`.  Partial replacement for the `ip`
and `brctl` commands; the modules in this package show info only.

Contains two modules:

  - [iptool](iptool): Lists interface info including IP addresses in a non-crazy format
  - [cpylmnl](cpylmnl): Submodle (https://github.com/unixnut/cpylmnl) forked from [chamaken/cpylmnl](https://github.com/chamaken/cpylmnl) in order to fix bugs

Installation
============

    git clone --recursive https://github.com/unixnut/iptool
    make -C iptool install

The second command creates a symlink in /usr/local/bin by default.
You can set `PREFIX` or `DEST` on the make command line to override this; see
[Makefile](Makefile).

