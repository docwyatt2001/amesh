#!/usr/bin/env python3

"""
A wireguard mesh control plane using Etcd3
"""

import os
import sys
import time
import configparser
import argparse
import subprocess
import uuid
import signal
import _thread

import etcd3

from enum import Enum

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


    
WGCMD = "/usr/bin/wg"
IPCMD = "/bin/ip"
ETCD_LEASE_TTL = 10
ETCD_LEASE_REFRESEH_INTERVAL = 5

class NodeState(Enum) :
    Init = 1
    Estab = 2

class Node (object) :
    
    def __init__(self, pubkey = None, endpoint = None, allowed_ips = [], 
                 keepalive = 0, wg_ip = None, groups = [], is_server = True) :
        self.pubkey = pubkey
        self.endpoint = endpoint
        self.allowed_ips = allowed_ips
        self.keepalive = keepalive
        self.wg_ip = wg_ip
        self.groups = groups
        self.is_server = is_server

        self.state = NodeState.Init

    def __str__(self) :
        return ("<Node: pubkey={}, endpoint={} groups={}>"
                .format(self.pubkey, self.endpoint, self.groups))

    def serialize_for_etcd(self, prefix = "", node_id = "") :
        p = "{}/{}".format(prefix, node_id)

        return {
            p + "/pubkey" : self.pubkey,
            p + "/endpoint" : str(self.endpoint),
            p + "/groups" : ",".join(self.groups),
            p + "/allowed_ips" : ",".join(self.allowed_ips),
            p + "/wg_ip" : self.wg_ip,
            p + "/keepalive" : str(self.keepalive),
            p + "/is_server" : str(self.is_server),
        }

    def update(self, key, value) :

        if value == "None" :
            value = None

        if key == "pubkey" :
            self.pubkey = value
        elif key == "endpoint" :
            self.endpoint = value
        elif key == "allowed_ips" :
            self.allowed_ips = value.strip().replace(" ", "").split(",")
        elif key == "keepalive" :
            self.keepalive = int(value)
        elif key == "wg_ip" :
            self.wg_ip = value
        elif key == "groups" :
            self.groups = value.strip().replace(" ", "").split(",")
        elif key == "is_server" :
            self.is_server = bool(value)
        else :
            raise ValueError("invalid key '{}' for value '{}'"
                             .format(key, value))

    def install(self, wg_dev, is_server) :

        # @is_server: bool, this amesh process is server or not

        if not self.pubkey :
            return

        if is_server or self.is_server :
            # install wg peer when either peer or this machine is a server

            cmd = [ WGCMD, "set", wg_dev, "peer", self.pubkey ]
            if self.endpoint :
                cmd += [ "endpoint", self.endpoint ]
            if self.allowed_ips :
                cmd += [ "allowed-ips", ",".join(self.allowed_ips) ]
            if self.keepalive :
                cmd += [ "persistent-keepalive", str(self.keepalive) ]
            subprocess.check_call(cmd)



    def remove(self, wg_dev) :

        cmd = [ WGCMD, "set", wg_dev, "peer", self.pubkey, "remove" ]
        subprocess.check_call(cmd)



class Amesh(object) :

    def __init__(self, config) :

        logger.info("load config and initialize amesh")

        # XXX: make node_table thread safe (currenty not locked!)
        self.node_table = {} # hash of nodes, key is pubkey, value is Node

        # thread-related 

        # Do Not catch exception here.
        self.etcd_endpoint = config.get("amesh", "etcd_endpoint")
        self.etcd_prefix = config.get("amesh", "etcd_prefix")
        self.etcd_node_id = str(uuid.uuid4())
        self.etcd_lease_id = None # assinged by etcd3.lease()

        self.wg_dev = config.get("wireguard", "wg_dev")
        self.wg_port = config.get("wireguard", "wg_port")
        self.prvkey = config.get("wireguard", "prvkey_file")

        pubkey = config.get("wireguard", "pubkey")
        endpoint = config.get("wireguard", "endpoint")
        endpoint = endpoint if endpoint != "None" else None
        is_server = True if config.get("amesh","is_server") == "yes" else False
        keepalive = int(config.get("wireguard", "keepalive"))
        allowed_ips = config.get("wireguard",
                                 "allowed_ips").replace(" ", "").split(",")


        wg_ip = config.get("wireguard", "wg_ip")
        groups = config.get("amesh", "groups").replace(" ", "").split(",")

        self.node = Node(pubkey = pubkey, endpoint = endpoint,
                         allowed_ips = allowed_ips, groups = groups,
                         keepalive = keepalive, wg_ip = wg_ip,
                         is_server = is_server)
        
        if (is_server and not endpoint) or (not is_server and endpoint) :
            logger.error("endpoint and is_server denpend on each other")
            raise ValueError("endpoint and is_server denpend on each other")

        logger.info("my node id is {}".format(self.etcd_node_id))
        logger.info("etcd prefix is {}".format(self.etcd_prefix))

        
    def init_wg_dev(self) :
        
        logger.info("set up wireguard interface {}".format(self.wg_dev))

        cmds = [
            [ IPCMD, "link", "add", self.wg_dev, "type", "wireguard" ],
            [ IPCMD, "link", "set", "dev", self.wg_dev, "up" ],
            [ IPCMD, "addr", "add", "dev", self.wg_dev, self.node.wg_ip ],
            [ WGCMD, "set", self.wg_dev,
              "private-key",  self.prvkey,
              "listen-port", self.wg_port,
            ]
        ]

        if os.path.exists("/sys/class/net/{}".format(self.wg_dev)) :
            cmds.insert(0, [ IPCMD, "link", "del", "dev", self.wg_dev ])

        for cmd in cmds :
            # Do not check exception. when fail, then crash the process.
            subprocess.check_call(cmd)

    def delete_wg_dev(self) :
        pass


    def etcd_client(self) :
        host, port = self.etcd_endpoint.split(":")
        return etcd3.client(host = host, port = port)

    def lease_maintainer(self) :

        failed = 0

        while True :

            time.sleep(ETCD_LEASE_REFRESEH_INTERVAL)
            try :
                etcd = self.etcd_client()
                lease = etcd3.Lease(self.etcd_lease_id, ETCD_LEASE_TTL,
                                    etcd_client = etcd)
                lease.refresh()
            except :
                # XXX: if etcd cluster is rebooted, the stored
                # values wiill disapper?
                logger.error("failed to update lease {0:x}: {1}"
                             .format(self.etcd_lease_id, sys.exc_info()))
                failed += 1
                
            if failed > ETCD_LEASE_TTL / ETCD_LEASE_REFRESEH_INTERVAL :
                logger.error("lease is revoked! start to retry to register")
                while True :
                    try :
                        self._lease_allocate()
                        self.register_for_etcd()
                        self.get_nodelist()
                        failed = 0
                        break
                    except :
                        logger.error("failed to re-register. try after {}sec."
                                     .format(ETCD_LEASE_REFRESEH_INTERVAL))
                        time.sleep(ETCD_LEASE_REFRESEH_INTERVAL)
                        continue


    def _lease_allocate(self) :

        etcd = self.etcd_client()
        self.etcd_lease_id = etcd.lease(ETCD_LEASE_TTL).id
        logger.info("etcd lease is {}".format(hex(self.etcd_lease_id)))


    def start_lease_maintainer(self) :
        
        self._lease_allocate()
        ret = _thread.start_new_thread(self.lease_maintainer, ())


    def register_for_etcd(self) :

        etcd = self.etcd_client()
        serialized = self.node.serialize_for_etcd(prefix = self.etcd_prefix,
                                                  node_id = self.etcd_node_id)
        for k, v in serialized.items() :
            etcd.put(k, v, lease = self.etcd_lease_id)


    def _update_node(self, node_id, key, value) :

        if not node_id in self.node_table :
            self.node_table[node_id]  = Node()

        self.node_table[node_id].update(key, value)

        try :
            self.node_table[node_id].install(self.wg_dev, self.node.is_server)
        except Exception as e :
            logger.error("failed to install node: {}".format(e))


    def _remove_node(self, node_id) :

        if node_id in self.node_table :
            node = self.node_table[node_id]

            try :
                if node.pubkey :
                    if node.endpoint :
                        self.node.remove(self.wg_dev)
                    del(self.node_table[node_id])
            except Exception as e :
                logger.error("failed to remove node: {}". format(e))
                
                

    def fill_node_table(self) :

        # get node information from etcd, and make self.node_table
        etcd = self.etcd_client()
        for value, meta in etcd.get_prefix(self.etcd_prefix) :
            
            # key is PREFIX/NODE_ID/KEY
            # note that node_id is a randomly created uuid per spawn
            # XXX: make own exception for parse error?
            try :
                prefix, node_id, key = meta.key.decode("utf-8").split("/")
            
                if node_id == self.etcd_node_id :
                    continue

                self._update_node(node_id, key, value.decode("utf-8"))

            except Exception as e :
                logger.error("fill_node_tabile failed on '{}': {}"
                             .format(meta.key.decode("utf-8"), e))
    
        # install nodes
        for node in self.node_table.values() :
            try :
                node.install(self.wg_dev, self.node.is_server)
            except Exception as e:
                logger.error("failed to install route for {} {}"
                             .format(node, e))


    def watch_node_info(self) :

        while True :

            try :
                etcd = self.etcd_client()
                event_iter, cancel = etcd.watch_prefix(self.etcd_prefix)

                for ev in event_iter :
                    prefix, node_id, key = ev.key.decode("utf-8").split("/")
                    if node_id == self.etcd_node_id : continue

                    if type(ev) is etcd3.events.PutEvent :
                        self._update_node(node_id,
                                          key, ev.value.decode("utf-8"))

                    elif type(ev) is etcd3.events.DeleteEvent :
                        self._remove_node(node_id)


            except Exception as e:
                logger.error("Node watch error: {}".format(e))
                logger.error("keye={}, value={}".format(ev.key, ev.value))
                continue


    def start_node_watcher(self) :
        self.watch_node_info()


if __name__ == "__main__" :

    parser = argparse.ArgumentParser()
    parser.add_argument("config", type = str,
                        help = "amesh config file")

    args = parser.parse_args()

    config = configparser.ConfigParser()
    # default values
    config.read_dict({
        "amesh" : {
            "etcd_endpoint" : "127.0.0.1:2379",
            "etcd_prefix" : "amesh",
            "is_server" : "yes",
        },
        "wireguard" : {
            "endpoint" : "None",
            "keepalive" : "0",
        },
    })

    config.read(args.config)

    amesh = Amesh(config)
    #signal.signal(signal.SIGINT, amesh.cleanup)

    amesh.init_wg_dev()
    amesh.start_lease_maintainer()
    amesh.register_for_etcd()
    amesh.fill_node_table()
    amesh.start_node_watcher()

    

