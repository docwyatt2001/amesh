

import subprocess

if not "amesh." in __name__ :
    from static import IPCMD, WGCMD, VERBOSE
else :
    from amesh.static import IPCMD, WGCMD, VERBOSE

from logging import getLogger, INFO, StreamHandler, Formatter
from logging.handlers import SysLogHandler
default_logger = getLogger(__name__)
default_logger.setLevel(INFO)
stream = StreamHandler()
syslog = SysLogHandler(address = "/dev/log")
default_logger.addHandler(stream)
default_logger.addHandler(syslog)
default_logger.propagate = False

class Node(object) :

    def __init__(self, 
                 dev = "wg0", pubkey = None, port = 5281,
                 endpoint = None, allowed_ips = [], keepalive = 0,
                 address = None, groups = set(), logger = None) :

        self.dev = dev
        self.pubkey = pubkey
        self.port = port
        self.endpoint = endpoint
        self.allowed_ips = allowed_ips
        self.keepalive = 0
        self.address = address
        self.groups = groups
        self.logger = logger or default_logger


    def __str__(self) :

        o = "<Node: pubkey={}, endpoint={}".format(self.pubkey, self.endpoint)
        
        if VERBOSE :
            o += ", alowed_ips={}".format(",".join(self.allowed_ips))
            o += ", keepalive={}".format(self.keepalive)
            o += ", groups={}".format(" ".join(sorted(list(self.groups))))

        o += ">"

        return  o


    def update(self, key, value) :

        if value == "None" :
            value = None

        if key == "dev" :
            self.dev = value
        elif key == "pubkey" :
            self.pubkey = value
        elif key == "port":
            self.port = int(value)
        elif key == "endpoint" :
            self.endpoint = value
        elif key == "allowed_ips" :
            if not value == "" :
                self.allowed_ips = value.strip().replace(" ", "").split(",")
        elif key == "keepalive" :
            self.keepalive = int(value)
        elif key == "address" :
            self.address = value
        elif key == "groups" :
            self.groups = set(value.strip().replace(" ", "").split(","))


    def deserialize(self, kvps) :

        """ deserialize(self, kvps)
        @kvps: key value pairs: list of (key, value). Note that key includes
               etcd_id/etcd_prefix
        """
        # decode and strip key and value bytes to utf8 string
        kvs = []
        for _key, value in kvps :
            etcd_prefix, etcd_id, key = key.decode("utf-8").split("/")
            kvs.append((key, value.decode("utf-8")))
        
        # update parameters
        for k, v in kvs :
            self.update(k, v)


    def serialize_for_etcd(self, etcd_prefix, node_id) :
        p = "{}/{}".format(etcd_prefix, node_id)
        
        return {
            p + "/dev" : self.dev,
            p + "/pubkey" : self.pubkey,
            p + "/port" : str(self.port),
            p + "/endpoint" : self.endpoint,
            p + "/allowed_ips" : ",".join(self.allowed_ips),
            p + "/keepalive" : str(self.keepalive),
            p + "/address" : self.address,
            p + "/groups" : ",".join(self.groups),
        }

        
    def install(self, wg_dev) :

        if not self.pubkey :
            return

        cmds = []

        wgcmd = [ WGCMD, "set", wg_dev, "peer", self.pubkey ]
        if self.endpoint :
            wgcmd += [ "endpoint", self.endpoint ]
        if self.allowed_ips :
            wgcmd += [ "allowed-ips", ",".join(self.allowed_ips) ]
        if self.keepalive :
            wgcmd += [ "persistent-keepalive", str(self.keepalive) ]

        cmds.append(wgcmd)

        for allowed_ip in self.allowed_ips :
            cmds.append([
                IPCMD, "route", "add", "to", allowed_ip, "dev", wg_dev,
            ])

        for cmd in cmds :
            subprocess.check_call(cmd)

        if self.logger :
            self.logger.debug("install node: {}"
                              .format(", ".join(map(lambda x: " ".join(x),
                                                    cmds))))

    def uninstall(self, wg_dev) :

        cmds = []

        wgcmd = [ WGCMD, "set", wg_dev, "peer", self.pubkey, "remove" ]
        cmds.append(wgcmd)

        for allowed_ip in self.allowed_ips :
            cmds.append([
                IPCMD, "route", "del", "to", allowed_ip,
            ])


        for cmd in cmds :
            subprocess.check_call(cmd)

        if self.logger :
            self.logger.debug("uninstall node: {}"
                              .format(", ".join(map(lambda x: " ".join(x),
                                                    cmds))))


