# General Network Troubleshooting

## Method

Start from the symptom and narrow it down layer by layer. First confirm that interfaces are up, then that neighbors can reach each other with ping on the directly connected addresses, then that the routing protocol adjacencies are formed, and finally that the expected routes are present in the routing table. Compare the configuration and state on both ends of every link that is involved. Most outages in a small lab are caused by a single setting that differs between two adjacent routers or by a filter that silently discards routes.

## Reachability tests

ping A.B.C.D tests reachability, and ping with a source address tests the return path, for example ping -I 10.255.0.1 10.255.0.4 from inside the container. traceroute shows where packets stop. When ping between loopbacks fails but ping between directly connected addresses works, the problem is in routing rather than in the link. When even directly connected pings fail, check the interface state and the addresses.

## Logs and telemetry

FRR writes protocol events to its log. OSPF logs adjacency changes, for example a neighbor going from Full to Down with the reason. BGP logs session changes and notifications sent or received. Telemetry collectors can periodically export interface counters, neighbor states and route counts so that a change in the number of routes or neighbors can be correlated with the time a fault started. A change of the route count on several routers at the same time usually points to one root cause close to the first router that changed.

## Recovery

After applying a fix, verify that the interface is up, that the OSPF neighbors are Full, that the BGP sessions are Established with the expected number of prefixes, and that loopback-to-loopback ping succeeds between all routers. Keep the change minimal and apply it only on the router that is wrong.
