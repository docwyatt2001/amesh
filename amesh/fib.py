
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

    def __init__(self, wg_dev, node, logger = None):

        self.wg_dev = wg_dev
        self.pubkey = node.pubkey
        self.endpoint = node.endpoint
        self.allowed_ips = node.allowed_ips
        self.keepalive = node.keepalive
        self.logger = logger or default_logger

    def __str__(self):

        return ("<Peer: pubkey={} endpoint={} allowed-ips={}>"
                .format(self.pubkey, self.endpoint, self.allowed_ips))

    def __eq__(self, other):

        return (self.wg_dev == other.wg_dev and
                self.pubkey == other.pubkey and
                self.endpoint == other.endpoint and
                self.allowed_ips == other.allowed_ips and
                self.keepalive == self.keepalive)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return int(uuid.uuid5(uuid.NAMESPACE_DNS,
                              "{}{}{}{}{}".format(self.wg_dev,
                                                  self.pubkey,
                                                  self.endpoint,
                                                  self.allowed_ips,
                                                  self.keepalive)))

    def install(self):

        if not self.pubkey:
            return

        wgcmd = [ WGCMD, "set", self.wg_dev, "peer", self.pubkey ]
        if self.endpoint:
            wgcmd += [ "endpoint", self.endpoint ]
        if self.allowed_ips:
            wgcmd += [ "allowed-ips", ",".join(self.allowed_ips) ]
        if self.keepalive:
            wgcmd += [ "persistent-keepalive", str(self.keepalive) ]

        try:
            subprocess.check_call(wgcmd)
            if self.logger:
                self.logger.debug("install peer: %s", " ".join(wgcmd))
        except Exception as e:
            self.logger.error("failed to install peer: %s", " ".join(wgcmd))


    def uninstall(self):

        if not self.pubkey:
            return

        wgcmd = [ WGCMD, "set", self.wg_dev, "peer", self.pubkey, "remove" ]
        try:
            subprocess.check_call(wgcmd)
            if self.logger:
                self.logger.debug("uninstall peer: %s", " ".join(wgcmd))
        except Exception as e:
            self.logger.error("failed to uninstall peer: %s", " ".join(wgcmd))


class Route(object):

    def __init__(self, wg_dev, prefix, logger = None):
        self.wg_dev = wg_dev
        self.prefix = prefix
        self.logger = logger or default_logger

    def __str__(self):
        return "<Route prefix={} dev={}>".format(self.prefix, self.wg_dev)

    def __eq__(self, other):
        return (self.wg_dev == other.wg_dev and
                self.prefix == other.prefix)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return int(uuid.uuid5(uuid.NAMESPACE_DNS,
                              "{}{}".format(self.wg_dev, self.prefix)))

    def install(self):
        ipcmd = [ IPCMD, "route", "add", "to",
                  self.prefix, "dev", self.wg_dev ]
        try:
            subprocess.check_call(ipcmd)
            if self.logger:
                self.logger.debug("install route: %s", " ".join(ipcmd))
        except Exception as e:
            self.logger.error("failed to instsall route: %s", " ".join(ipcmd))

    def uninstall(self):
        ipcmd = [ IPCMD, "route", "del", "to",
                  self.prefix, "dev", self.wg_dev ]
        try:
            subprocess.check_call(ipcmd)
            if self.logger:
                self.logger.debug("uninstall route: %s", " ".join(ipcmd))
        except Exception as e:
            self.logger.error("failed to uninstall route: %s", " ".join(ipcmd))


class Fib(object):

    """
    Forwarding Information Base:
    This Fib contains actual wireguard peer configs and IP routing
    table entries that have peers' allowed-ips as destination prefix
    and wiregaurd evice as output interface.
    """

    def __init__(self, self_node, node_table, logger = None):

        self.self_node = self_node
        self.peers = set()
        self.routes = set()
        self.logger = logger or default_logger

        # calculate wg peers and allowed-ips as routes from node_table
        for node_id, node in node_table.items():

            if self.check_group(node):

                self.peers.add(Peer(self.self_node.dev, node,
                                    logger = self.logger))

                for allowed_ip in node.allowed_ips:
                    self.routes.add(Route(self.self_node.dev, allowed_ip,
                                          logger = self.logger))


    def __str__(self):
        return ("<" +
                " ".join(map(str, list(self.peers))) + " " +
                " ".join(map(str, list(self.routes))) +
                ">")

    def check_group(self, node):
        return ("any" in self.self_node.groups | node.groups or
                self.self_node.groups & node.groups)


    def update_diff(self, old):

        # Step 1, Remove peers that are in old, but not in self
        removed_peers = old.peers - self.peers
        for removed_peer in removed_peers:
            removed_peer.uninstall()

        # Step 2, Add peers that are not in old, but int self
        added_peers = self.peers - old.peers
        for added_peer in added_peers:
            added_peer.install()

        # Step 3, Remove routes that are in old, but not in self
        removed_routes = old.routes - self.routes
        for removed_route in removed_routes:
            removed_route.uninstall()

        # Step 4, Add routes that are not in old, but in self
        added_routes = self.routes - old.routes
        for added_route in added_routes:
            added_route.install()


    def uninstall(self):

        for peer in self.peers:
            peer.uninstall()

        for route in self.routes:
            route.uninstall()
