# OSPF Hello and Dead Timers

## Hello interval and dead interval

ip ospf hello-interval SECONDS sets how often Hello packets are sent on the interface; the default is 10 seconds. ip ospf dead-interval SECONDS sets how long the router waits without receiving a Hello before declaring the neighbor down; the default is 40 seconds, four times the hello interval. no ip ospf hello-interval and no ip ospf dead-interval restore the defaults. ip ospf dead-interval minimal hello-multiplier N enables sub-second Hellos.

## Timer mismatch

The HelloInterval and RouterDeadInterval carried in a Hello packet must be identical on both routers of a link. If they differ, the receiving router discards the Hello and the adjacency never forms, or an existing adjacency goes down after the dead interval expires. The OSPF log shows a message such as "Packet 10.0.12.1 [Hello:RECV]: HelloInterval mismatch" or "RouterDeadInterval mismatch". In show ip ospf interface the Timer intervals line shows the configured Hello and Dead values, which can be compared between the two routers. Note that the symptom of a timer mismatch on an existing adjacency only appears after the dead interval, so the neighbor can stay Full for up to 40 seconds after the change.

## Fixing a timer mismatch

Find the router whose timers differ from the rest of the network, enter the interface node and set the timers back to the agreed values, for example ip ospf hello-interval 10 and ip ospf dead-interval 40, or remove the custom value with no ip ospf hello-interval. The dead interval must always be larger than the hello interval. After the change, the neighbor goes from Init to Full within a few seconds, which can be confirmed with show ip ospf neighbor.
