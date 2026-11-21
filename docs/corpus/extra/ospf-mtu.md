# OSPF and Interface MTU

## MTU check during database exchange

OSPF includes the interface MTU in Database Description (DBD) packets. When a router receives a DBD packet advertising an MTU larger than its own interface MTU, it rejects the packet. As a result, the adjacency is stuck in the ExStart or Exchange state and never reaches Full, while Hello packets are still exchanged normally so the neighbor is visible. The OSPF log shows a message such as "Packet[DD]: Neighbor 10.255.0.2 MTU 1500 is larger than [eth1:10.0.12.1]'s MTU 1400". An MTU mismatch is the most common cause of a neighbor stuck in ExStart/Exchange.

## Symptoms outside OSPF

With an MTU mismatch, small pings between the two routers succeed but large pings fail, for example ping -s 1472 -M do fails while ping -s 100 works. BGP sessions over the link may establish and then stall when large UPDATE messages are sent. In show interface the MTU field shows the configured value, so the MTU of both ends can be compared directly.

## Fixing an MTU mismatch

In a Linux or containerlab router the MTU is a kernel property of the interface. It is changed with ip link set dev IFNAME mtu 1500 inside the container; zebra picks up the new value automatically. The MTU must be equal on both ends of the link, normally 1500 bytes for Ethernet. As a workaround, ip ospf mtu-ignore inside the interface node makes OSPF ignore the MTU field in DBD packets, but this hides the real problem and large packets will still be dropped. The preferred remediation is to set the interface MTU back to the value used by the neighbor.
