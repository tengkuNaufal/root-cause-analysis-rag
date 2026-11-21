# Zebra: Interface Configuration

## Interface commands

The interface IFNAME command enters the configuration node of an interface. Inside this node the operator can assign addresses, add a description, and change the administrative state. zebra keeps track of every interface reported by the Linux kernel, including its operational state, its addresses and its flags. Interfaces in a containerlab topology are veth pairs, so the two ends of a link appear as eth1, eth2 and so on inside the two router containers. The loopback interface lo carries the router ID address and is commonly used as the source of iBGP sessions. The description LINE command adds free text to the interface. The link-detect command makes zebra follow the carrier state of the interface so that routes over it are withdrawn when the link goes down.

## Addresses

The ip address A.B.C.D/M command configures an IPv4 address on the interface, and no ip address A.B.C.D/M removes it. Both ends of a point-to-point link must be configured in the same subnet, for example 10.0.12.1/30 and 10.0.12.2/30. If one side is configured with an address from another subnet, the connected route on the two routers no longer overlaps, ARP between the neighbors fails and the routing protocols cannot exchange packets. OSPF will refuse Hello packets whose source address is not on the receiving interface's network and logs a message about the source not being on the interface network. When changing an address, first remove the wrong address with no ip address and then configure the correct one, otherwise the interface ends up with two addresses.

## Administrative state

The shutdown command administratively disables an interface and no shutdown enables it again. An interface that is administratively down is reported in show interface as admin down, carries no traffic, and every routing protocol adjacency over it is torn down immediately. On Linux the same effect can be obtained with ip link set dev IFNAME down and reversed with ip link set dev IFNAME up. When an interface goes down, zebra withdraws the connected route, OSPF removes the neighbor and floods new LSAs, and a BGP session using that link drops when its hold timer expires or immediately if fast external failover is enabled. To restore the interface, enter the interface node and issue no shutdown, then verify that the state is up with show interface brief.

## Interface show commands

show interface IFNAME prints the state, the MTU, the hardware address, the configured addresses and the packet counters. show interface brief summarizes all interfaces. Counters that increase for input errors or drops may indicate a physical or configuration problem. The kernel view can be compared with ip -br link and ip -br addr inside the container.
