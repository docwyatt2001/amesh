#/bin/bash


nsname=netns3
vrf=vrf-wg
ipns="ip netns exec $nsname"

$ipns ip link add $vrf type vrf table 10
$ipns ip addr add dev $vrf 172.16.11.3/32
$ipns ip link set dev $vrf up
$ipns ip link set dev dummy0 master $vrf
$ipns ip link set dev dummy1 master $vrf
