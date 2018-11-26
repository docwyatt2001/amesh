#/bin/bash

set -e

ipns="ip netns exec"
ping="ping -c 3"

echo
echo PING FROM netns2 to netns1
$ipns netns2 $ping 172.16.1.1

echo
echo PING FROM netns1 to netns2
$ipns netns1 $ping 172.16.1.2

echo
echo PING FROM netns3 to netns1
$ipns netns3 $ping 172.16.1.1

echo
echo PING FROM netns1 to netns3
$ipns netns1 $ping 172.16.1.3

echo
echo PING FROM netns4 to netns1
$ipns netns4 $ping 172.16.1.1


echo
echo PING FROM netns2 to netns4
$ipns netns2 $ping 172.16.1.4

echo
echo PING FROM netns4 to netns2
$ipns netns4 $ping 172.16.1.2

echo
echo PING FROM netns3 to netns4
$ipns netns3 $ping 172.16.1.4

echo
echo PING FROM netns4 to netns3
$ipns netns4 $ping 172.16.1.3

