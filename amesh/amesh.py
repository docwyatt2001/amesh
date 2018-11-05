
import os
import time
import uuid
import subprocess
import threading

import etcd3

if not "amesh." in __name__:
    from node import Node
    from fib import Fib
    from static import (IPCMD, WGCMD,
                        ETCD_LEASE_LIFETIME,
                        ETCD_LEASE_KEEPALIVE)
else:
    from amesh.node import Node
    from amesh.fib import Fib
    from amesh.static import (IPCMD, WGCMD,
                              ETCD_LEASE_LIFETIME,
                              ETCD_LEASE_KEEPALIVE)


from logging import getLogger, INFO, StreamHandler
from logging.handlers import SysLogHandler
default_logger = getLogger(__name__)
default_logger.setLevel(INFO)
stream = StreamHandler()
syslog = SysLogHandler(address = "/dev/log")
default_logger.addHandler(stream)
default_logger.addHandler(syslog)
default_logger.propagate = False

class Amesh(object):

    def __init__(self, cnf, logger = None):

        self.logger = logger or default_logger

        self.logger.info("Load config and initialize amesh")

        # node_table: hash of nodes, key is etcd id, value is Node
        self.node_table = {}

        # self node parameteres
        self.node = Node()

        # mode
        if not "mode" in cnf["amesh"]:
            err = "mode does not specified"
            self.logger.error(err)
            raise RuntimeError(err)
        if not cnf["amesh"]["mode"] in ("adhoc", "controlled"):
            err = "invalid mode '{}'".format(cnf["amesh"]["mode"])
            self.logger.error(err)
            raise RuntimeError(err)
        self.mode = cnf["amesh"]["mode"]

        # etcd parameters
        self.etcd_endpoint = cnf["amesh"]["etcd_endpoint"]
        self.etcd_prefix = cnf["amesh"]["etcd_prefix"]

        # private key file
        self.wg_prvkey_path = cnf["wireguard"]["prvkey_path"]

        # public key file
        with open(cnf["wireguard"]["pubkey_path"], "r") as f:
            pubkey = f.read().strip()
        self.node.update("pubkey", pubkey)

        # node id is specified or generated from pubkey
        if "node_id" in cnf["amesh"]:
            self.node_id = cnf["amesh"]["node_id"]
        else:
            self.node_id = str(uuid.uuid3(uuid.NAMESPACE_DNS,
                                          self.node.pubkey))


        # parameters in adhoc mode
        if self.mode == "adhoc":
            self.node.update("dev", cnf["wireguard"]["device"])
            self.node.update("port", cnf["wireguard"]["port"])

            if "address" in cnf["wireguard"]:
                self.node.update("address", cnf["wireguard"]["address"])

            if "endpoint" in cnf["wireguard"]:
                self.node.update("endpoint", cnf["wireguard"]["endpoint"])

            if "keepalive" in cnf["wireguard"]:
                self.node.update("keepalive", cnf["wireguard"]["keepalive"])

            if "allowed_ips" in cnf["wireguard"]:
                self.node.update("allowed_ips",
                                 cnf["wireguard"]["allowed_ips"])

            if "groups" in cnf["amesh"]:
                self.node.update("groups", cnf["amesh"]["groups"])


        # etcd lease for adhoc mode
        self.etcd_lease = None

        # initialize Fib
        self.fib = Fib(self.node, {}, logger = self.logger)


        # thread cancel events
        self.th_maintainer = threading.Thread(target = self.etcd_maintainer)
        self.th_watcher = threading.Thread(target = self.etcd_watcher)
        self.stop_maintainer = threading.Event()
        self.stop_watcher = threading.Event()
        self.cancel_watcher = None # cancel of etcd3.watch_prefix()

        self.logger.debug("mode:           %s", self.mode)
        self.logger.debug("node_id:        %s", self.node_id)
        self.logger.debug("etcd endpoint:  %s", self.etcd_endpoint)
        self.logger.debug("etcd prefix:    %s", self.etcd_prefix)
        self.logger.debug("wg device:      %s", self.node.dev)
        self.logger.debug("wg prvkey path: %s", self.wg_prvkey_path)
        self.logger.debug("wg pubkey:      %s", self.node.pubkey)

        if self.mode == "adhoc":
            self.logger.debug("wg address:     %s", self.node.address)
            self.logger.debug("wg port:        %s", self.node.port)
            self.logger.debug("wg endpoint:    %s", self.node.endpoint)
            self.logger.debug("wg keepalive:   %s", self.node.keepalive)
            self.logger.debug("wg allowed_ips: %s", self.node.allowed_ips)
            self.logger.debug("amesh groups:   %s", self.node.groups)


    def start(self):
        if self.mode == "adhoc":
            self.init_wg_dev()
            self.th_maintainer.start()
        self.th_watcher.start()

    def join(self):
        if self.mode == "adhoc":
            self.th_maintainer.join()
        self.th_watcher.join()

        self.logger.info("uninstall routes...")
        self.fib.uninstall()


    def cancel(self):

        self.logger.info("stopping amesh...")

        if self.mode == "adhoc":
            self.stop_maintainer.set()

        self.stop_watcher.set()
        if self.cancel_watcher:
            self.cancel_watcher()

    def init_wg_dev(self):

        self.logger.info("set up wireguard interface %s", self.node.dev)

        cmds = []

        # check prvkey can be opened
        try:
            f = open(self.wg_prvkey_path, "r")
            f.close()
        except Exception as e:
            self.logger.error(e)

        if not os.path.exists("/sys/class/net/{}".format(self.node.dev)):
            cmds.append([ IPCMD, "link", "add", self.node.dev,
                          "type", "wireguard" ],)

        cmds += [
            [ IPCMD, "link", "set", "dev", self.node.dev, "up" ],
            [ IPCMD, "addr", "flush", "dev", self.node.dev ],
            [ WGCMD, "set", self.node.dev,
              "private-key",  self.wg_prvkey_path,
              "listen-port", str(self.node.port),
            ]
        ]

        if self.node.address:
            cmds.append([ IPCMD, "addr", "add", "dev", self.node.dev,
                          self.node.address ])

        for cmd in cmds:
            # Do not check exception. when fail, then crash the process.
            subprocess.check_call(cmd)


    def etcd_client(self):
        host, port = self.etcd_endpoint.split(":")
        return etcd3.client(host = host, port = port)


    def etcd_lease_allocate(self):
        etcd = self.etcd_client()
        self.etcd_lease = etcd.lease(ETCD_LEASE_LIFETIME)
        self.logger.debug("allocated etcd lease is %x", self.etcd_lease.id)


    def etcd_register(self):
        etcd = self.etcd_client()
        d = self.node.serialize_for_etcd(self.etcd_prefix, self.node_id)
        for k, v in d.items():
            etcd.put(k, v, lease = self.etcd_lease.id)


    def etcd_maintainer(self):

        connected = True

        while True:
            try:
                if self.stop_maintainer.is_set():
                    return

                self.etcd_lease_allocate()
                self.etcd_register()
                cnt = 0

                connected = True
                self.logger.info("etcd maintainer connected to %s",
                                 self.etcd_endpoint)

                while True:
                    time.sleep(1)

                    if self.stop_maintainer.is_set():
                        return

                    cnt += 1
                    if cnt % ETCD_LEASE_KEEPALIVE == 0:
                        self.etcd_lease.refresh()
                        cnt = 0

            except etcd3.exceptions.Etcd3Exception as e:
                if connected:
                    self.logger.error("etcd maintainer failed: %s",
                                      e.__class__)
                    connected = False
                time.sleep(1)


    def etcd_watcher(self):

        connected = True

        while True:

            try:
                if self.stop_watcher.is_set():
                    return

                # initialize node_table
                self.node_table = {}
                self.etcd_obtain()

                etcd = self.etcd_client()
                wtach_prefix = "{}/".format(self.etcd_prefix)

                event_iter, cancel = etcd.watch_prefix(wtach_prefix)
                self.cancel_watcher = cancel

                connected = True
                self.logger.info("etcd watch connected to %s",
                                 self.etcd_endpoint)

                for ev in event_iter:
                    _, node_id, key = ev.key.decode("utf-8").split("/")
                    value = ev.value.decode("utf-8")
                    if type(ev) == etcd3.events.PutEvent:
                        ev_type = "put"
                    else:
                        ev_type = "delete"
                    self.process_etcd_kv(node_id, key, value, ev_type)

            except etcd3.exceptions.Etcd3Exception as e:
                if connected:
                    self.logger.error("etcd watch failed: %s", e.__class__)
                    connected = False

                self.cancel_watcher = None
                time.sleep(1)


    def etcd_obtain(self):

        etcd = self.etcd_client()

        for value, meta in etcd.get_prefix(self.etcd_prefix):
            _, node_id, key = meta.key.decode("utf-8").split("/")
            value = value.decode("utf-8")
            self.process_etcd_kv(node_id, key, value, "put")


    def process_etcd_kv(self, node_id, key, value, ev_type):

        self.logger.debug("k/v: ev_type=%s, node_id=%s, key=%s, value=%s",
                          ev_type, node_id, key, value)

        if node_id == self.node_id:
            self.update_self(key, value, ev_type)
        else:
            self.update_other(node_id, key, value, ev_type)


    def update_self(self, key, value, ev_type):

        if self.mode != "controlled":
            return

        if ev_type == "delete":
            return self.remove_self(key, value)

        configure_wg_dev = False
        configure_peers = False

        # update myself
        changed = self.node.update(key, value)

        if key in ("address", "endpoint"):
            configure_wg_dev = True
        elif key in ("groups"):
            configure_peers = True
        elif key in ("dev", "pubkey", "port"):
            configure_wg_dev = True
            configure_peers = True

        if self.node.is_present() and changed and configure_wg_dev:
            self.init_wg_dev()

        if self.node.is_present() and changed and configure_peers:
            new_fib = Fib(self.node, self.node_table, logger = self.logger)
            new_fib.update_diff(self.fib)
            self.fib = new_fib


    def update_other(self, node_id, key, value, ev_type):

        changed = False

        if ev_type == "put":
            changed = self.update_node(node_id, key, value)

        elif ev_type == "delete":
            changed = self.remove_node(node_id)

        if self.node.is_present() and changed:
            new_fib = Fib(self.node, self.node_table, logger = self.logger)
            new_fib.update_diff(self.fib)
            self.fib = new_fib


    def update_node(self, node_id, key, value):

        if not node_id in self.node_table:
            self.node_table[node_id] = Node(logger = self.logger)

        node = self.node_table[node_id]
        changed = node.update(key, value)
        return changed


    def remove_node(self, node_id):

        if not node_id in self.node_table:
            changed = False
        else :
            node = self.node_table[node_id]
            del self.node_table[node_id]
            changed = True

        return changed


    def remove_self(self, key, value) :

        if not self.node.is_present():
            return

        self.logger.info("my id is removed. make me absent and uninstall Fib.")

        self.fib.uninstall()
        self.fib = Fib(self.node, {}, logger = self.logger)
        self.node.make_absent()
