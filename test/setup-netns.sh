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
	ipns="ip netns exec $nsname"
	intfa=$nsname-a
	intfb=$nsname-b
	phy_ip=172.16.0.$nsnum/24
	dummy_ip=172.16.1.$nsnum/32

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

	$ipns ip link set dev lo up
	$ipns ip link set dev $intfb up
	$ipns ip addr add dev $intfb $phy_ip

	$ipns ip link add dummy0 type dummy
	$ipns ip link set dev dummy0 up
	$ipns ip addr add dev dummy0 $dummy_ip

	# for device tracking test
	$ipns ip link add dummy1 type dummy
	$ipns ip link set dev dummy1 up
done

