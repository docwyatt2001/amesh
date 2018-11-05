
# Amesh: a wireguard mesh control plane

## What is this

Amesh is a control plane for [Wiregaurd](https://www.wireguard.com/).
Amesh constructs a mesh-like topology using wiregaurd as a data plane
and etcd as a distributed configuration repositry.


## Install

```
% git clone https://github.com/upa/amesh.git
% sudo pip3 install .
```

## Quick Start

```
% cd /usr/local/etc/amesh
% cp amesh.conf.sample amesh.conf
% amesh -h
usage: amesh [-h] [-d] [-c CONFIG]

optional arguments:
  -h, --help            show this help message and exit
  -d, --debug           enable debug logs
  -c CONFIG, --config CONFIG
                        amesh config file. default is
                        /usr/local/etc/amesh/amesh.conf
% sudo amesh
```

### How to configure amesh.


## ToDo

- clustering and scurity on etcd
- testing
- README
