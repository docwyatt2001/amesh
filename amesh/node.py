

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

    def __init__(self, pubkey = None, endpoint = None, allowed_ips = [],
                 keepalive = 0, groups = set(), logger = None) :

        self.pubkey = pubkey
        self.endpoint = endpoint
        self.allowed_ips = allowed_ips
        self.keepalive = 0
        self.groups = groups
        self.logger = logger or default_logger


    def __str__(self) :

        o = "<Node: pubkey={}, endpoint={}".format(self.pubkey, self.endpoint)
        
        if VERBOSE :
            o += ", alowed_ips={}".format(",".join(allowed_ips))
            o += ", keepalive={}".format(self.keepalive)
            o += ", groups={}".format(" ".join(sorted(list(self.groups))))

        o += ">"

        return  o


    def update(self, key, value) :

        if value == "None" :
            value = None

        if key == "pubkey" :
            self.pubkey = value
        elif key == "endpoint" :
            self.endpoint = value
        elif key == "allowed_ips" :
            if not value == "" :
                self.allowed_ips = value.strip().replace(" ", "").split(",")
        elif key == "keepalive" :
            self.keepalive = int(value)
        elif key == "groups" :
            self.groups = set(value.strip().replace(" ", "").split(","))
        else :
            raise ValueError("invalid key '{}' for value '{}'"
                             .format(key, value))

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


    def serialize_for_etcd(self, etcd_id, etcd_prefix) :
        p = "{}/{}".format(etcd_prefix, etcd_id)
        
        return {
            p + "/pubkey" : self.pubkey,
            p + "/endpoint" : self.endpoint,
            p + "/allowed_ips" : ",".join(self.allowed_ips),
            p + "/keepalive" : str(self.keepalive),
            p + "/groups" : ",".join(self.groups),
        }

        
    def install(self, wg_dev) :

        if not self.pubkey :
            return

        cmd = [ WGCMD, "set", wg_dev, "peer", self.pubkey ]
        if self.endpoint :
            cmd += [ "endpoint", self.endpoint ]
        if self.allowed_ips :
            cmd += [ "allowed-ips", ",".join(self.allowed_ips) ]
        if self.keepalive :
            cmd += [ "persistent-keepalive", str(self.keepalive) ]
        subprocess.check_call(cmd)

        if self.logger :
            self.logger.debug("install node: {}".format(" ".join(cmd)))


    def uninstall(self, wg_dev) :

        cmd = [ WGCMD, "set", wg_dev, "peer", self.pubkey, "remove" ]
        subprocess.check_call(cmd)

        if self.logger :
            self.logger.debug("uninstall node: {}".format(" ".join(cmd)))


