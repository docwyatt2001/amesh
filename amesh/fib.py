
import os
import subprocess
import uuid

if not "amesh." in __name__:
    from node import Node
    from static import WGCMD, IPCMD
else:
    from amesh.node import Node
    from amesh.static import WGCMD, IPCMD

from logging import getLogger, INFO, StreamHandler
from logging.handlers import SysLogHandler
default_logger = getLogger(__name__)
default_logger.setLevel(INFO)
stream = StreamHandler()
syslog = SysLogHandler(address = "/dev/log")
default_logger.addHandler(stream)
default_logger.addHandler(syslog)
default_logger.propagate = False

class Peer(object):

    def __init__(self, wg_dev, node, outbound = False,
                 prvkey_path = None, logger = None):
        """
        Peer:
        @wg_dev: wireugard device name for this peer
        @node: Node class for this peer
        @outbound: Peer for incomming connection or not
        @prvkey_path: private key path for egress wg device for this peer
        @logger: logger
        """

        self.wg_dev = wg_dev
        self.outbound = outbound

        self.pubkey = node.pubkey
        self.endpoint = node.endpoint
        self.allowed_ips = node.allowed_ips
        self.keepalive = node.keepalive

        self.prvkey_path = prvkey_path

        self.logger = logger or default_logger

    def __str__(self):

        return ("<Peer: hash={} pubkey={} endpoint={} allowed-ips={}>"
                .format(self.__hash__(),
                        self.pubkey, self.endpoint, self.allowed_ips))

    def __eq__(self, other):

        return (self.wg_dev == other.wg_dev and
                self.outbound == other.outbound and
                self.pubkey == other.pubkey and
                self.endpoint == other.endpoint and
                self.allowed_ips == other.allowed_ips and
                self.keepalive == self.keepalive)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return int(uuid.uuid5(uuid.NAMESPACE_DNS,
                              "{}{}{}{}{}{}".format(self.wg_dev,
                                                      self.outbound,
                                                      self.pubkey,
                                                      self.endpoint,
                                                      self.allowed_ips,
                                                      self.keepalive)))

    def install(self):

        if not self.pubkey:
            return

        cmds = []

        if self.outbound:
            # this peer is an oubbound peer for a server (it has an endpoint).
            # thus, create the wg device and use it for egress connections
            if os.path.exists("/sys/class/net/{}".format(self.wg_dev)):
                cmds.append([ IPCMD, "link", "del", "dev", self.wg_dev ])
            cmds += [
                [ IPCMD, "link", "add", self.wg_dev, "type", "wireguard" ],
                [ IPCMD, "link", "set", "dev", self.wg_dev, "up" ],
                [ WGCMD , "set", self.wg_dev, "private-key", self.prvkey_path ]
            ]

        wgcmd = [ WGCMD, "set", self.wg_dev, "peer", self.pubkey ]
        if self.endpoint:
            wgcmd += [ "endpoint", self.endpoint ]
        if self.allowed_ips:
            wgcmd += [ "allowed-ips", ",".join(map(str, self.allowed_ips)) ]
        if self.keepalive:
            wgcmd += [ "persistent-keepalive", str(self.keepalive) ]

        cmds.append(wgcmd)

        self.logger.debug("install peer: %s", " ".join(map(str, cmds)))
        for cmd in cmds:
            try:
                subprocess.check_call(map(str, cmd))
            except Exception as e:
                self.logger.error("failed to install peer: %s", " ".join(cmd))


    def uninstall(self):

        if not self.pubkey:
            return

        cmds = [
            [ WGCMD, "set", self.wg_dev, "peer", self.pubkey, "remove" ],
        ]

        if self.outbound:
            # this peer is an oubbound peer for a server (it has an endpoint).
            # thus, remove the outbound wg device.
            cmds.append([ IPCMD, "link", "del", "dev", self.wg_dev])

        self.logger.debug("uninstall peer: %s", " ".join(map(str, cmds)))
        for cmd in cmds:
            try:
                subprocess.check_call(map(str, cmd))
            except Exception as e:
                self.logger.error("failed to uninstall peer: \n%s",
                                  " ".join(cmd))


class Route(object):

    def __init__(self, wg_dev, prefix, logger = None):
        self.wg_devs = [ wg_dev ]
        self.prefix = str(prefix)
        self.logger = logger or default_logger

        self.removed = False
        # removed is a flag that indicates this route will be removed
        # because of peer is uninstalled (and wg device is removed).
        # this flag changes hash of this object, so that
        # the same route in new FIB will be installed.

    def __str__(self):
        return "<Route hash={} prefix={} dev={}>".format(self.__hash__(),
                                                         self.prefix,
                                                         self.wg_devs)

    def __eq__(self, other):
        return (self.wg_devs == other.wg_devs and
                self.prefix == other.prefix and
                self.removed == other.removed)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return int(uuid.uuid5(uuid.NAMESPACE_DNS,
                              "{}{}{}".format(self.wg_devs, self.prefix,
                                              self.removed)))

    def append_nexthop_dev(self, wg_dev):
        if wg_dev in self.wg_devs:
            return
        self.wg_devs.append(wg_dev)

    def check_dev(self, wg_dev):
        return (wg_dev in self.wg_devs)

    def make_this_removed(self):
        self.removed = True

    def install(self):

        ipcmd = [ IPCMD, "route", "add", "to", self.prefix ]

        for wg_dev in self.wg_devs:
            ipcmd += [ "nexthop", "dev", wg_dev ]

        try:
            subprocess.check_call(ipcmd)
            self.logger.debug("install route: %s", " ".join(ipcmd))
        except Exception as e:
            self.logger.error("failed to install route: %s", " ".join(ipcmd))

    def uninstall(self):

        ipcmd = [ IPCMD, "route", "del", "to", self.prefix ]

        try:
            subprocess.check_call(ipcmd)
            self.logger.debug("uninstall route: %s", " ".join(ipcmd))
        except Exception as e:
            self.logger.error("failed to uninstall route: %s", " ".join(ipcmd))



class Fib(object):

    def __init__(self, wg_dev, self_node, node_table, prvkey_path,
                 logger = None):
        """
        Fib:
        @wg_dev: wg device for incomming connections
        @self_node: Node describing self (check my groups and ednpoints)
        @node_table: dict of Node instances
        @prvkey_path: wireguard private key path
        """

        self.wg_dev = wg_dev
        self.groups = self_node.groups
        self.peers = set()
        self.routes = set()
        self.routes_dict = {}

        # prvkey for dedicated wg devices for outbound conncetions
        self.prvkey_path = prvkey_path

        self.logger = logger or default_logger

        # calculate wg peers and allowed-ips as routes from node_table
        for node_id, node in node_table.items():

            if not node.pubkey:
                continue

            if not node.endpoint and not self_node.endpoint:
                # Both self and this node DO NOT have endpoints.
                # Thus, we are client mode, and do not install routes.
                continue

            if not self.check_group(node):
                # group does not match
                continue


            wg_dev = self.wg_dev

            # Peer for outbound connection if the node is a server
            if node.endpoint:
                wg_dev = "wg-{}".format(node.pubkey)[:13]
                self.peers.add(Peer(wg_dev, node,
                                    outbound = True,
                                    prvkey_path = self.prvkey_path,
                                    logger = self.logger))

            # Peer for incoming connection because i am a server
            if self_node.endpoint:
                self.peers.add(Peer(self.wg_dev, node, logger = self.logger))

            #  routing table entries
            for allowed_ip in node.allowed_ips:

                # check this prefix already exists
                # if exist, append the device as a nexthop for ECMP
                # if not, create a new route entry
                if allowed_ip in self.routes_dict:
                    self.routes_dict[allowed_ip].append_nexthop_dev(wg_dev)
                else:
                    route = Route(wg_dev, allowed_ip, logger = self.logger)
                    self.routes.add(route)
                    self.routes_dict[allowed_ip] = route


    def __str__(self):
        return ("<" +
                " ".join(map(str, list(self.peers))) + " " +
                " ".join(map(str, list(self.routes))) +
                ">")

    def check_group(self, node):
        return ("any" in self.groups | node.groups or
                self.groups & node.groups)


    def update_diff(self, old):

        """
        print("Old Peers")
        print("\n".join(map(str, old.peers)))

        print("New Peers")
        print("\n".join(map(str, self.peers)))

        print("Old Routes")
        print("\n".join(map(str, old.routes)))

        print("New Routes")
        print("\n".join(map(str, self.routes)))
        """

        # Step 1, Remove peers that are in old, but not in new Fib,
        # and check routes associated with the removed peers
        removed_peers = old.peers - self.peers
        for removed_peer in removed_peers:

            removed_peer.uninstall()

            if removed_peer.outbound:
                for route in self.routes:
                    if route.check_dev(removed_peer.wg_dev):
                        # this associated route is also removed automatically
                        # by linux kernel because the wg interface for
                        # this outbound connction is removed.
                        route.make_this_removed()


        # Step 2, Remove routes that are in old, but not in new Fib
        # routes, which hav removed = True, are already removed
        # at last step.
        removed_routes = old.routes - self.routes
        for removed_route in removed_routes:
            if not removed_route.removed:
                removed_route.uninstall()


        # Step 3, Add peers that are not in old, but in new Fib
        added_peers = self.peers - old.peers
        for added_peer in added_peers:
            added_peer.install()

        # Step 4, Add routes that are not in old, but in new Fib
        added_routes = self.routes - old.routes
        for added_route in added_routes:
            added_route.install()


    def uninstall(self):

        for route in self.routes:
            route.uninstall()

        for peer in self.peers:
            peer.uninstall()

