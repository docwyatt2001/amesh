
# Amesh: A wireguard mesh control plane

## What is this

Amesh is a control plane for [Wiregaurd](https://www.wireguard.com/).
Amesh constructs a mesh-like topology using wiregaurd as a data plane
and etcd as a control plane.


## Install

```
% git clone https://github.com/upa/amesh.git
% sudo pip3 install .
```


## Quick Start

```
% sudo amesh /usr/local/etc/amesh/amesh.conf
```

### How to configure amesh.


## ToDo

- clustering and scurity on etcd
- testing
- README
