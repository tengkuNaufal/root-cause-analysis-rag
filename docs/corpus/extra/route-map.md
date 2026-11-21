# Route Maps

## Structure

route-map NAME permit|deny SEQ creates an entry of a route map. Each entry can contain match clauses, such as match ip address prefix-list LIST, and set clauses, such as set local-preference 200 or set metric 50. Entries are evaluated in sequence order. A route that matches a permit entry is accepted and modified by its set clauses; a route that matches a deny entry is rejected. A route map ends with an implicit deny, so a route map that contains only a deny entry without any match clause rejects every route. no route-map NAME deny SEQ removes one entry and no route-map NAME removes the whole map.

## Applying a route map to a BGP neighbor

Inside router bgp and address-family ipv4 unicast, neighbor PEER route-map NAME in applies the map to routes received from the peer, and neighbor PEER route-map NAME out applies it to routes advertised to the peer. An outbound deny route-map stops the router from advertising its prefixes, so the remote router has an Established session but receives zero prefixes from it. An inbound deny route-map discards everything the peer sends. In both cases the BGP session stays up, which makes the fault harder to see than a session failure.

## Fixing a deny route map

Check show ip bgp neighbors PEER for the route-map bound in each direction and show route-map NAME for the entries and their match counts. Remove the binding with no neighbor PEER route-map NAME in|out, or remove the offending entry with no route-map NAME deny SEQ, then refresh the routes with clear ip bgp PEER soft out for outbound policy or soft in for inbound policy. Confirm that show ip bgp neighbors PEER advertised-routes lists the expected prefixes again.
