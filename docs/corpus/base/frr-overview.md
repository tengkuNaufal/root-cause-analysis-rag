# FRRouting Overview

## Daemons and processes

FRRouting (FRR) is a routing protocol suite for Linux and Unix platforms. Each routing protocol runs as its own daemon: zebra manages the kernel interface and routing table, ospfd implements OSPFv2, bgpd implements BGP-4, and staticd handles static routes. The daemons talk to zebra over the ZAPI socket. zebra installs the best routes from every protocol into the Linux kernel forwarding table. The watchfrr daemon monitors the other daemons and restarts them if they crash. Which daemons are started is controlled by the file /etc/frr/daemons, where each protocol is set to yes or no. When running FRR inside containers, for example in a containerlab topology, each router is a container that runs zebra, ospfd, bgpd and staticd together, and the configuration is stored in /etc/frr/frr.conf as an integrated configuration file.

## The vtysh shell

vtysh is the integrated shell that connects to all running daemons at once. A command typed in vtysh is forwarded to the daemon that owns it. vtysh can be used interactively or non-interactively with the -c option, for example vtysh -c "show ip route". Several -c options can be chained to run a sequence of commands, which is how automation tools push configuration. When automating, every configuration sequence normally starts with configure terminal, followed by the context command such as interface or router ospf, followed by the actual settings. The end command returns to the exec mode. The write memory command saves the running configuration to the integrated configuration file so it survives a restart.

## Configuration modes

FRR follows a Cisco-like command line hierarchy. Exec mode allows show and clear commands. configure terminal enters the global configuration node. From there, interface IFNAME enters the interface node, router ospf enters the OSPF node, router bgp ASN enters the BGP node, and route-map NAME permit|deny SEQ enters a route-map entry. Inside the BGP node, address-family ipv4 unicast enters the IPv4 unicast address family. The exit command leaves the current node and returns to its parent; exit-address-family leaves the address family. If a command is not valid in the current node, vtysh tries the parent node, so a user can type router ospf directly while still inside an interface node.

## Useful show commands

show running-config prints the active configuration. show interface brief lists interfaces with their status and addresses. show ip route lists the routing table with the protocol that installed each route, for example O for OSPF and B for BGP. show ip ospf neighbor lists OSPF neighbors and their adjacency state. show bgp summary lists BGP peers, their state and the number of received prefixes. show logging and the log file in /var/log/frr give the daemon messages that explain why a protocol is not converging. Operators should always compare the state on both ends of a link because most faults are caused by a configuration that differs between the two routers.
