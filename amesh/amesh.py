
import os
import time
import uuid
import logging
import subprocess
import threading

import etcd3

if not "amesh." in __name__ :
    from node import Node
    from static import (IPCMD, WGCMD,
                        ETCD_LEASE_LIFETIME,
                        ETCD_LEASE_KEEPALIVE,
                        ETCD_RECONNECT_INTERVAL)
else :
    from amesh.node import Node
    from amesh.static import (IPCMD, WGCMD,
                              ETCD_LEASE_LIFETIME,
                              ETCD_LEASE_KEEPALIVE,
                              ETCD_RECONNECT_INTERVAL)


from logging import getLogger, INFO, StreamHandler, Formatter
from logging.handlers import SysLogHandler
default_logger = getLogger(__name__)
default_logger.setLevel(INFO)
stream = StreamHandler()
syslog = SysLogHandler(address = "/dev/log")
default_logger.addHandler(stream)
default_logger.addHandler(syslog)
default_logger.propagate = False

class Amesh(object) :

    def __init__(self, config_dict, logger = None) :

        self.logger = logger or default_logger

        self.logger.info("Load config and initialize amesh")

        # node_table: hash of nodes, key is etcd id, value is Node
        self.node_table = {}

        # mode
        if not "mode" in config_dict["amesh"] :
            err = "mode does not specified"
            self.logger.error(err)
            raise RuntimeError(err)
        if not config_dict["amesh"]["mode"] in ("adhoc", "controlled") :
            err = "invalid mode '{}'".format(config_dict["amesh"]["mode"])
            self.logger.error(err)
            raise RuntimeError(err)
        self.mode = config_dict["amesh"]["mode"]


        # parameters in both adhoc and controlled modes
        # wg_addr (None) is needed for init_wg_dev()
        self.wg_dev = config_dict["wireguard"]["device"]
        self.wg_pubkey = config_dict["wireguard"]["pubkey"]
        self.wg_prvkey_path = config_dict["wireguard"]["prvkey_path"]
        self.wg_addr = None
        self.wg_port = int(config_dict["wireguard"]["port"])
        self.groups = set([])

        self.etcd_endpoint = config_dict["amesh"]["etcd_endpoint"]         
        self.etcd_prefix = config_dict["amesh"]["etcd_prefix"]
        if "node_id" in config_dict["amesh"] :
            self.node_id = config_dict["amesh"]["node_id"]
        else :
            self.node_id = str(uuid.uuid3(uuid.NAMESPACE_DNS, self.wg_pubkey))


        # parameters in only adhoc mode
        if self.mode == "adhoc" :
            if not "address" in config_dict["wireguard"] :
                err = "address in [wireguard] is not specified"
                self.logger.error(err)
                raise RuntimeError(err)
            self.wg_addr = config_dict["wireguard"]["address"]

            if "endpoint" in config_dict["wireguard"]:
                self.wg_endpoint = config_dict["wireguard"]["endpoint"]
            else :
                self.wg_endpoint = None

            self.wg_keepalive = int(config_dict["wireguard"]["keepalive"])


            if "allowed_ips" in config_dict["wireguard"] :
                self.allowed_ips = config_dict["wireguard"]["allowed_ips"]\
                    .replace(" ", "").split(",")
            else :
                self.allowed_ips = []

            if "groups" in config_dict["amesh"] :
                self.groups = set(config_dict["amesh"]["groups"]
                                  .replace(" ", "").split(","))
            else :
                self.groups = set()
            
        # etcd lease for adhoc mode
        self.etcd_lease = None

        # thread cancel events
        self.th_maintainer = threading.Thread(target = self.etcd_maintainer)
        self.th_watcher = threading.Thread(target = self.etcd_watcher)
        self.stop_maintainer = threading.Event()
        self.stop_watcher = threading.Event()
        self.cancel_watcher = None # cancel of etcd3.watch_prefix()

        self.logger.debug("mode:           {}".format(self.mode))
        self.logger.debug("node_id:        {}".format(self.node_id))
        self.logger.debug("etcd endpoint:  {}".format(self.etcd_endpoint))
        self.logger.debug("etcd prefix:    {}".format(self.etcd_prefix))
        self.logger.debug("wg device:      {}".format(self.wg_dev))
        self.logger.debug("wg prvkey path: {}".format(self.wg_prvkey_path))
        self.logger.debug("wg pubkey:      {}".format(self.wg_pubkey))

        if self.mode == "adhoc" :
            self.logger.debug("wg address:     {}".format(self.wg_addr))
            self.logger.debug("wg port:        {}".format(self.wg_port))
            self.logger.debug("wg endpoint:    {}".format(self.wg_endpoint))
            self.logger.debug("wg keepalive:   {}".format(self.wg_keepalive))
            self.logger.debug("wg allowed_ips: {}".format(self.allowed_ips))
            self.logger.debug("amesh groups:   {}".format(self.groups))


    def start(self) :
        self.init_wg_dev()
        if self.mode == "adhoc" :
            self.th_maintainer.start()
        self.th_watcher.start()
    
    def join(self) :
        if self.mode == "adhoc" :
            self.th_maintainer.join()
        self.th_watcher.join()

    def cancel(self) :

        self.logger.info("stopping amesh...")

        if self.mode == "adhoc" :
            self.stop_maintainer.set()

        self.stop_watcher.set()
        if self.cancel_watcher :
            self.cancel_watcher()

    def init_wg_dev(self) :

        self.logger.info("set up wireguard interface {}".format(self.wg_dev))

        cmds = []

        # check prvkey can be opened
        try :
            f = open(self.wg_prvkey_path, "r")
            f.close()
        except Exception as e:
            err = "failed to read {}".format(self.wg_prvkey_path)
            self.logger.error(err)
            raise RuntimeError(err)
            

        if not os.path.exists("/sys/class/net/{}".format(self.wg_dev)) :
            cmds.append([ IPCMD, "link", "add", self.wg_dev,
                          "type", "wireguard" ],)

        cmds += [
            [ IPCMD, "link", "set", "dev", self.wg_dev, "up" ],
            [ IPCMD, "addr", "flush", "dev", self.wg_dev ],
            [ WGCMD, "set", self.wg_dev,
              "private-key",  self.wg_prvkey_path,
              "listen-port", str(self.wg_port),
            ]
        ]

        if self.wg_addr :
            cmds.append([ IPCMD, "addr", "add", "dev", self.wg_dev,
                          self.wg_addr ])

        for cmd in cmds :
            # Do not check exception. when fail, then crash the process.
            subprocess.check_call(cmd)


    def etcd_client(self) :
        host, port = self.etcd_endpoint.split(":")
        return etcd3.client(host = host, port = port)


    def etcd_lease_allocate(self) :
        etcd = self.etcd_client()
        self.etcd_lease = etcd.lease(ETCD_LEASE_LIFETIME)
        self.logger.debug("allocated etcd lease is {:x}"
                          .format(self.etcd_lease.id))


    def etcd_register(self) :
        etcd = self.etcd_client()
        node_self = Node(pubkey = self.wg_pubkey,
                         port = self.wg_port,
                         endpoint = self.wg_endpoint,
                         allowed_ips = self.allowed_ips,
                         keepalive = self.wg_keepalive,
                         address = self.wg_addr,
                         groups = self.groups,
                         logger = self.logger)

        d = node_self.serialize_for_etcd(self.etcd_prefix, self.node_id)
        for k, v in d.items() :
            etcd.put(k, v, lease = self.etcd_lease.id)


    def etcd_maintainer(self) :

        connected = True

        while True :
            try :
                if self.stop_maintainer.is_set() :
                    return

                self.etcd_lease_allocate()
                self.etcd_register()
                cnt = 0
                
                connected = True
                self.logger.info("etcd maintainer conncted to {}"
                                 .format(self.etcd_endpoint))

                while True :
                    time.sleep(1)

                    if self.stop_maintainer.is_set() :
                        return
                        
                    cnt += 1
                    if cnt % ETCD_LEASE_KEEPALIVE == 0:
                        self.etcd_lease.refresh()
                        cnt = 0

            except etcd3.exceptions.Etcd3Exception as e:
                if conncted :
                    self.logger.error("etcd maintainer failed: {}"
                                      .format(e.__class__))
                    connected = False
                time.sleep(1)


    def etcd_watcher(self) :

        connected = True

        while True :

            try :
                if self.stop_watcher.is_set() :
                    return

                # initialize node_table
                self.node_table = {}
                self.etcd_obtain()

                etcd = self.etcd_client()
                wtach_prefix = "{}/".format(self.etcd_prefix)

                event_iter, cancel = etcd.watch_prefix(wtach_prefix)
                self.cancel_watcher = cancel

                connected = True
                self.logger.info("etcd watch connected to {}"
                                 .format(self.etcd_endpoint))

                for ev in event_iter :
                    prefix, node_id, key = ev.key.decode("utf-8").split("/")
                    value = ev.value.decode("utf-8")
                    if type(ev) == etcd3.events.PutEvent :
                        ev_type = "put"
                    else :
                        ev_type = "delete"
                    self.process_etcd_kv(node_id, key, value, ev_type)

            except etcd3.exceptions.Etcd3Exception as e:
                if connected :
                    self.logger.error("etcd watch failed: {}"
                                      .format(e.__class__))
                    connected = False
                self.cancel_watcher = None
                time.sleep(1)
                

    def etcd_obtain(self) :

        etcd = self.etcd_client()

        for value, meta in etcd.get_prefix(self.etcd_prefix) :
            preifx, node_id, key = meta.key.decode("utf-8").split("/")
            value = value.decode("utf-8")
            self.process_etcd_kv(node_id, key, value, "put")


    def process_etcd_kv(self, node_id, key, value, ev_type) :

        self.logger.debug("process key/value: node_id={}, key={}, value={}"
                     .format(node_id, key, value))

        if node_id == self.node_id :
            self.update_self(key, value)
        else :
            self.update_other(node_id, key, value, ev_type)


    def update_self(self, key, value) :

        if self.mode != "controlled" :
            return

        configure_wg_dev = False
        configure_peers = False

        # in controlled mode, update self parameters
        if value == "None" :
            value = None

        try :
            if key == "address" :
                self.wg_addr = value
                configure_wg_dev = True
            elif key == "port" :
                self.wg_port = int(value)
                configure_wg_dev = True
            elif key == "endpoint" :
                self.wg_endpoint = value
                # nothing to do
            elif key == "allowed_ips" :
                if value == "" :
                    self.allowed_ips = []
                else :
                    self.allowed_ips = value.strip()\
                                            .replace(" ", "").split(",")
                # XXX: how to use allowed_ips?
                # install static route to peer wg_addr ?
            elif key == "groups" :
                self.groups = set(value.replace(" ", "").split(","))
                configure_peers = True

        except Exception as e :
            self.logger.error("failed to update self: key={}, value={}"
                              .format(key, value))
            return
            
        if configure_wg_dev :
            self.init_wg_dev()
        
        if configure_peers :
            for node in self.node_table.values() :
                try :
                    node.uninstall(self.wg_dev)
                except :
                    pass
                node.install(self.wg_dev)


    def update_other(self, node_id, key, value, ev_type) :

        if node_id == self.node_id :
            self.update_self(key, value)

        if ev_type is "put" :
            try :
                self.update_node(node_id, key, value)
            except Exception as e :
                self.logger.error("failed to update {}: {}".format(node_id, e))
                          

        elif ev_type is "delete" :
            try :
                self.remove_node(node_id)
            except Exception as e :
                self.logger.error("failed to remove {}: {}".format(node_id, e))


    def check_group(self, group_a, group_b) :
        if "any" in group_a | group_b or group_a & group_b :
            return True
        return False


    def update_node(self, node_id, key, value) :

        if not node_id in self.node_table :
            self.node_table[node_id] = Node(logger = self.logger)

        node = self.node_table[node_id]
        node.update(key, value)

        if self.check_group(self.groups, node.groups) :
            node.install(self.wg_dev)


    def remove_node(self, node_id) :

        if not node_id in self.node_table :
            return

        node = self.node_table[node_id]

        if self.check_group(self.groups, node.groups) :
            node.uninstall(self.wg_dev)
        del(self.node_table[node_id])
