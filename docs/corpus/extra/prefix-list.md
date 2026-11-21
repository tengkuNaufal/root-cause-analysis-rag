# IP Prefix Lists

## Syntax

ip prefix-list NAME seq N permit|deny A.B.C.D/M [ge G] [le L] defines one entry of a prefix list. Entries are evaluated in increasing sequence order and the first match decides. ge and le match a range of prefix lengths; for example 10.255.0.0/24 le 32 matches the /24 and every longer prefix inside it, and 0.0.0.0/0 le 32 matches every IPv4 prefix. A prefix list ends with an implicit deny, so a list that only contains deny entries blocks every prefix. no ip prefix-list NAME seq N removes one entry and no ip prefix-list NAME removes the whole list.

## Applying a prefix list to a BGP neighbor

Inside router bgp and address-family ipv4 unicast, neighbor PEER prefix-list NAME in filters the routes received from the peer, and neighbor PEER prefix-list NAME out filters the routes advertised to the peer. A deny entry that matches the peer's prefixes causes the session to stay Established while the number of received prefixes drops to zero, and the routes learned from that peer disappear from show ip route. Loopbacks of the remote AS become unreachable even though the BGP session itself looks healthy.

## Fixing a blocking prefix list

Identify the filter with show ip bgp neighbors PEER, which lists the inbound and outbound prefix lists, and show ip prefix-list NAME, which shows the entries and their hit counts. Remove the binding with no neighbor PEER prefix-list NAME in (or out), or correct the entry, then run clear ip bgp PEER soft in (or soft out) so the routes are re-evaluated without resetting the session. Verify with show bgp summary that the received prefix count is back to the expected value.
