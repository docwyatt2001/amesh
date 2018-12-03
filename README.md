
# Amesh: a wireguard mesh control plane

## What is this

Amesh is a control plane for [Wiregaurd](https://www.wireguard.com/).
Amesh constructs a mesh-like topology using wiregaurd as a data plane
and etcd as a distributed configuration repositry.


## Install

```
% git clone https://github.com/upa/amesh.git
% cd amesh
% sudo pip3 install .
```

## Quick Start

```
# install etcd for a data repository
% sudo apt install etcd

# install wireguard. see https://www.wireguard.com/install/

# setup configurations

% cd /usr/local/etc/amesh
% cp amesh.conf.sample amesh.conf

# Edit /usr/local/etc/amesh/amesh.conf
# and create wiregaurd private and public keys
% vim amesh.conf
% wg genkey > private.key
% wg pubkey < private.key > public.key


% amesh -h
usage: amesh [-h] [-d] [-f] [-c CONFIG]

optional arguments:
  -h, --help            show this help message and exit
  -d, --debug           enable debug logs
  -f, --foreground-log  enable foreground logs
  -c CONFIG, --config CONFIG
                        amesh config file. default is
                        /usr/local/etc/amesh/amesh.conf
% sudo amesh -df
```


### using amesh through systemd
```
% sudo systemctl enable amesh.service
% sudo systemctl start amesh
```

/etc/default/amesh can specify option arguments. Make the file, and
write the AMESH_OPTS variable.

Note that amesh depends on some sysctl parameters shown below.

- net.ipv4.ip_forward=1
- net.ipv4.conf.default.rp_filter=0
- net.ipv4.conf.all.rp_filter=0

And we recommend,

- net.ipv4.fib_multipath_use_neigh=1
- net.ipv4.fib_multipath_hash_policy=1


### How to configure amesh.

TDB.
see etc/amesh.conf.sample.


## ToDo

- clustering and scurity on etcd
- testing
- Document
