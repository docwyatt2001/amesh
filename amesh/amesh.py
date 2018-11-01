#!/usr/bin/env python3

import os
import time
import uuid
import logging
import subprocess

import etcd3
import amesh_node

from static import IPCMD, WGCMD

from logging import getLogger, DEBUG, StreamHandler, Formatter
from logging.handlers import SysLogHandler
logger = getLogger(__name__)
logger.setLevel(DEBUG)
stream = StreamHandler()
syslog = SysLogHandler(address = "/dev/log")
syslog.setFormatter(Formatter("amesh: %(message)s"))
logger.addHandler(stream)
logger.addHandler(syslog)
logger.propagate = False

class Amesh(object) :

    def __init__(self, config_dict) :

        logger.info("Load config and initialize amesh")

        # node_table: hash of nodes, key is etcd id, value is Node
        self.node_table = {}

        self.wg_dev = config_dict["wireguard"]["device"]
        if not "address" in config_dict["wireguard"] :
            logger.error("address in [wireguard] is not specified")
            raise RuntimeError("address in [wireguard] is not specified")
        self.wg_addr = config_dict["wireguard"]["address"]

        self.wg_port = config_dict["wireguard"]["port"]
        if "endpoint" in config_dict["wireguard"]:
            self.wg_endpoint = config_dict["wireguard"]["endpoint"]
        else :
            self.wg_endpoint = None

        self.wg_prvkey_path = config_dict["wireguard"]["prvkey_path"]
        self.wg_pubkey = config_dict["wireguard"]["pubkey"]
        self.wg_keepalive = int(config_dict["wireguard"]["keepalive"])

        self.etcd_endpoint = config_dict["amesh"]["etcd_endpoint"] 
        self.etcd_prefix = config_dict["amesh"]["etcd_prefix"]
        if "node_id" in config_dict["amesh"] :
            self.node_id = config_dict["amesh"]["node_id"]
        else :
            self.node_id = str(uuid.uuid3(uuid.NAMESPACE_DNS, self.wg_pubkey))

        # overwritable params
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
            

        logger.debug("node_id:        {}".format(self.node_id))
        logger.debug("etcd endpoint:  {}".format(self.etcd_endpoint))
        logger.debug("etcd prefix:    {}".format(self.etcd_prefix))
        logger.debug("wg device:      {}".format(self.wg_dev))
        logger.debug("wg address:     {}".format(self.wg_addr))
        logger.debug("wg port:        {}".format(self.wg_port))
        logger.debug("wg endpoint:    {}".format(self.wg_endpoint))
        logger.debug("wg prvkey path: {}".format(self.wg_prvkey_path))
        logger.debug("wg pubkey:      {}".format(self.wg_pubkey))
        logger.debug("wg keepalive:   {}".format(self.wg_keepalive))
        logger.debug("wg allowed_ips: {}".format(self.allowed_ips))
        logger.debug("amesh groups:   {}".format(self.groups))


    def init_wg_dev(self) :

        logger.info("set up wireguard interface {}".format(self.wg_dev))

        cmds = [
            [ IPCMD, "link", "add", self.wg_dev, "type", "wireguard" ],
            [ IPCMD, "link", "set", "dev", self.wg_dev, "up" ],
            [ IPCMD, "addr", "add", "dev", self.wg_dev, self.wg_addr ],
            [ WGCMD, "set", self.wg_dev,
              "private-key",  self.wg_prvkey_path,
              "listen-port", self.wg_port,
            ]
        ]

        if os.path.exists("/sys/class/net/{}".format(self.wg_dev)) :
            cmds.insert(0, [ IPCMD, "link", "del", "dev", self.wg_dev ])

        for cmd in cmds :
            # Do not check exception. when fail, then crash the process.
            subprocess.check_call(cmd)

    def etcd_client(self) :
        host, port = self.etcd_endpoint.split(":")
        return etcd3.client(host = host, port = port)


    def etcd_register(self) :
        etcd = self.etcd_client()
        node_self = amesh_node.Node(pubkey = self.wg_pubkey,
                                    endpoint = self.wg_endpoint,
                                    allowed_ips = self.allowed_ips,
                                    keepalive = self.wg_keepalive,
                                    groups = self.groups)

        d = node_self.serialize_for_etcd(self.node_id, self.etcd_prefix)
        for k, v in d.items() :
            etcd.put(k, v)

    def etcd_watch(self) :

        while True :

            try :
                self.node_table = {}
                self.etcd_obtain()
                self.etcd_register()

                etcd = self.etcd_client()
                wtach_prefix = "{}/".format(self.etcd_prefix)

                event_iter, cancel = etcd.watch_prefix(wtach_prefix)

                for ev in event_iter :
                    prefix, node_id, key = ev.key.decode("utf-8").split("/")
                    value = ev.value.decode("utf-8")
                    if type(ev) == etcd3.events.PutEvent :
                        ev_type = "put"
                    else :
                        ev_type = "delete"
                    self.process_etcd_kv(node_id, key, value, ev_type)

            except etcd3.exceptions.ConnectionFailedError as e:
                logger.error("etcd connection failed".format(e))
                time.sleep(1)
                

    def etcd_obtain(self) :

        etcd = self.etcd_client()

        for value, meta in etcd.get_prefix(self.etcd_prefix) :
            preifx, node_id, key = meta.key.decode("utf-8").split("/")
            value = value.decode("utf-8")
            self.process_etcd_kv(node_id, key, value, "put")



    def process_etcd_kv(self, node_id, key, value, ev_type) :

        logger.debug("process key/value: nodei_id={}, key={}, value={}"
                     .format(node_id, key, value))

        if node_id == self.node_id :
            self.update_self(key, value)
        else :
            self.update_other(node_id, key, value, ev_type)


    def update_self(self, key, value) :

        if key == "groups" :
            self.groups = set(value.split(","))
            # XXX: trigger update FIB

        elif key == "allowed_ips" :
            self.allowed_ips = value.split(",")


    def update_other(self, node_id, key, value, ev_type) :

        if node_id == self.node_id :
            self.update_self(key, value)

        if ev_type is "put" :
            try :
                self.update_node(node_id, key, value)
            except Exception as e :
                logger.error("failed to update {}: {}".format(node_id, e))
                          

        elif ev_type is "delete" :
            try :
                self.remove_node(node_id)
            except Exception as e :
                logger.error("failed to remove {}: {}".format(node_id, e))


    def check_group(self, group_a, group_b) :
        if "any" in group_a | group_b or group_a & group_b :
            return True
        return False

    def update_node(self, node_id, key, value) :

        if not node_id in self.node_table :
            self.node_table[node_id] = amesh_node.Node()

        node = self.node_table[node_id]
        node.update(key, value)

        if self.check_group(self.groups, node.groups) :
            node.install(self.wg_dev)

    def remove_node(self, node_id) :

        if not node_id in self.node_table :
            return

        if self.check_group(self.groups, node.groups) :
            node.uninstall(self.wg_dev)
