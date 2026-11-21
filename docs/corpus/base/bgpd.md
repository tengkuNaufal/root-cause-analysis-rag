# BGP (bgpd)

## Starting BGP

router bgp ASN enters the BGP configuration node for the local autonomous system number. bgp router-id A.B.C.D sets the router ID. A peer is created with neighbor PEER remote-as ASN, where PEER is the address of the neighbor. If ASN equals the local AS the session is internal BGP (iBGP); otherwise it is external BGP (eBGP). The keywords internal and external can be used instead of a number. iBGP sessions are usually established between loopback addresses, which requires neighbor PEER update-source lo so the TCP session is sourced from the loopback.

## Address families

Since FRR 7, IPv4 unicast prefixes are configured inside address-family ipv4 unicast. The network A.B.C.D/M command advertises a prefix if it exists in the routing table. Policies that apply to a neighbor, such as filters and route-maps, are configured inside the address family with neighbor PEER followed by the policy command. Changes to inbound policy take effect after the routes are re-evaluated, which can be triggered with clear ip bgp PEER soft in; changes to outbound policy require clear ip bgp PEER soft out.

## Session states

A BGP session goes through the states Idle, Connect, Active, OpenSent, OpenConfirm and Established. show bgp summary shows the state of each peer; when a peer is Established the column shows the number of prefixes received instead of a state name. A peer that stays in Active or Idle cannot open the TCP connection or keeps rejecting the OPEN message. A session that is Established but shows zero received prefixes indicates that the peer is not sending routes or that an inbound filter is discarding them.

## Filtering overview

BGP routes can be filtered with prefix-lists, route-maps and AS-path access lists. Filters are attached per neighbor and per direction, inbound or outbound. Without any filter, eBGP in FRR follows RFC 8212 and requires a policy to be configured unless bgp ebgp-requires-policy is disabled. Filters are evaluated in order and the first match decides the result. Details of each filter type are described in their own sections.

## Verifying routes

show ip bgp lists the BGP table with the best path marked with >. show ip bgp neighbors PEER advertised-routes and received-routes show what is exchanged with a peer; received-routes requires soft-reconfiguration inbound. show ip bgp neighbors PEER prints the session details including the last error and the notification that closed the session.
