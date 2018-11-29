### test script

modify the sysctl.conf and `sysctl -p`
```
net.ipv4.ip_forward=1
net.ipv4.conf.default.rp_filter=0
net.ipv4.conf.all.rp_filter=0
net.ipv4.fib_multipath_use_neigh=1
net.ipv4.fib_multipath_hash_policy=1
```

1. sudo ./setup-netns.sh
  - configure network namespaces for test
2. sudo tmux new-session \; source-file start-ameshes-tmux
  - start amesh processes on each network namespace
3. sudo ./start-ping-check.sh
  - check ping between namespaces

netns1 and netns4 are server hosts, which have endpoints.
netns2 and netns3 are client hosts, which do not have endpoints.

netns1 and netns4 perform redundancy and load-balancing for
172.16.1.0/24 prefix on wireguard overlay.
