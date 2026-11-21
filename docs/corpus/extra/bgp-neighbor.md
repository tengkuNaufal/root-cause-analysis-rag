# BGP Neighbor Configuration and Errors

## remote-as must match the peer

neighbor PEER remote-as ASN must contain the AS number that the peer actually uses. During session setup each router sends an OPEN message with its own AS number. If the received AS does not match the configured remote-as, the router sends a NOTIFICATION with error "OPEN Message Error / Bad Peer AS" and closes the session. The session then cycles between Idle, Active and OpenSent and never becomes Established. The log shows "bad OPEN, remote AS is 65002, expected 65020". show ip bgp neighbors PEER displays the configured remote AS and the last notification.

## Fixing a wrong remote-as

Enter router bgp with the local ASN and configure neighbor PEER remote-as with the correct peer AS, for example neighbor 10.0.34.2 remote-as 65002. In FRR the new value replaces the old one and the session is restarted automatically. The local AS of the peer can be found in the peer's router bgp line, in the topology documentation, or in the notification message.

## Other neighbor settings

neighbor PEER update-source IFNAME selects the source address of the TCP session; iBGP between loopbacks requires update-source lo on both routers. neighbor PEER ebgp-multihop N is needed when eBGP peers are not directly connected. neighbor PEER timers KEEPALIVE HOLDTIME changes the BGP timers; the defaults are 60 and 180 seconds in traditional profile and 3 and 9 seconds in the datacenter profile. neighbor PEER password sets TCP MD5 authentication, which must match on both sides. neighbor PEER shutdown administratively disables a session and no neighbor PEER shutdown enables it again.

## Diagnosing a session that is down

When a session is not Established, check in order: IP reachability of the peer address, the remote-as on both sides, the update-source for loopback peerings, the multihop setting for non-connected eBGP peers, and the password. The last error in show ip bgp neighbors PEER usually names the reason.
