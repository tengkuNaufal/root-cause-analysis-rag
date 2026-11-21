# OSPFv2 (ospfd)

## Enabling OSPF

The router ospf command enters the OSPF configuration node. ospf router-id A.B.C.D sets the router ID, normally equal to the loopback address. OSPF can be enabled on interfaces in two ways. With network A.B.C.D/M area AREA inside router ospf, every interface whose address falls in the prefix joins the given area. Alternatively, ip ospf area AREA inside the interface node enables OSPF on that single interface. The two methods should not be mixed on the same interface. The area can be written in dotted decimal form such as 0.0.0.0 or as a number such as 0; both refer to the backbone area.

## Interface parameters

Many OSPF parameters are set per interface: ip ospf cost, ip ospf hello-interval, ip ospf dead-interval, ip ospf retransmit-interval, ip ospf transmit-delay, ip ospf priority, ip ospf network point-to-point, ip ospf mtu-ignore, ip ospf authentication and ip ospf passive. The network type controls whether a designated router is elected. Point-to-point links between two routers usually use ip ospf network point-to-point to speed up adjacency formation. Changing a parameter on only one side of a link may prevent the adjacency from forming, so parameters that must match should be changed on both routers.

## Areas

An OSPF area is a set of routers that share the same link-state database. Two routers on the same link must place that link in the same area. If one router puts the interface in area 0.0.0.0 and the other in area 0.0.0.1, Hello packets are discarded and the log shows an area mismatch message. The neighbor never appears in show ip ospf neighbor. To fix an area mismatch, remove the wrong area with no ip ospf area and configure the correct area on the interface, or correct the network statement under router ospf.

## Passive interfaces

passive-interface IFNAME inside router ospf, or ip ospf passive inside the interface node, makes OSPF advertise the interface network but stop sending and receiving Hello packets on it. This is used on loopbacks and on links towards hosts. If a transit link between two routers is accidentally made passive, the adjacency over it disappears and routes that depended on it are recalculated over other paths or lost. The fix is no passive-interface IFNAME or no ip ospf passive.

## Authentication

OSPF supports simple password authentication and MD5 authentication. ip ospf authentication enables simple authentication with ip ospf authentication-key KEY. ip ospf authentication message-digest enables MD5 with ip ospf message-digest-key KEYID md5 KEY. Authentication can also be enabled for a whole area with area AREA authentication. Both routers on a link must use the same authentication type and the same key; otherwise Hello packets are dropped and the log reports an authentication type mismatch or an MD5 authentication error. Removing authentication on the misconfigured side with no ip ospf authentication restores the adjacency if the other side does not use authentication.

## Neighbor states

show ip ospf neighbor displays the neighbor state. Down means no Hello was received. Init means a Hello was received but the router did not see itself in it. 2-Way means bidirectional communication. ExStart and Exchange are used to negotiate and exchange the database description. Loading requests missing LSAs, and Full means the databases are synchronized. A neighbor that never leaves Init or that disappears periodically points to a parameter mismatch, while a neighbor stuck in ExStart or Exchange points to a problem during database exchange.
