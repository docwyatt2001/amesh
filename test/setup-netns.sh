#!/bin/bash

br=test-br
amesh=~/work/amesh/amesh/main.py
configdir=~/work/amesh/test


if [ -e /sys/class/net/$br ]; then
	ip link del dev $br
fi

ip link add $br type bridge
ip link set dev $br up
ip addr add dev $br 172.16.0.100/24


for nsnum in 1 2 3 4; do

	nsname=netns$nsnum
	intfa=$nsname-a
	intfb=$nsname-b
	phy_ip=172.16.0.$nsnum/24
	wg_ip=172.16.1.$nsnum/32

	if [ -e /sys/class/net/$intfa ]; then
		ip link del dev $intfa
	fi

	if [ -e /var/run/netns/$nsname ]; then
		ip netns del $nsname
	fi


	ip netns add $nsname
	ip link add $intfa type veth peer name $intfb
	ip link set dev $intfa up
	ip link set dev $intfa master $br
	ip link set dev $intfb netns $nsname

	ip netns exec $nsname ip link set dev lo up
	ip netns exec $nsname ip link set dev $intfb up

	ip netns exec $nsname ip addr add dev $intfb $phy_ip
	ip netns exec $nsname ip link add wg0 type wireguard
	ip netns exec $nsname ip link set dev wg0 up
	ip netns exec $nsname ip addr add dev wg0 $wg_ip
done

