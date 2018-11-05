

import subprocess

if not "amesh." in __name__:
    from static import IPCMD, WGCMD, VERBOSE
else:
    from amesh.static import IPCMD, WGCMD, VERBOSE

from logging import getLogger, INFO, StreamHandler
from logging.handlers import SysLogHandler
default_logger = getLogger(__name__)
default_logger.setLevel(INFO)
stream = StreamHandler()
syslog = SysLogHandler(address = "/dev/log")
default_logger.addHandler(stream)
default_logger.addHandler(syslog)
default_logger.propagate = False

class Node(object):

    def __init__(self,
                 dev = "wg0", pubkey = None, port = 5281,
                 endpoint = None, allowed_ips = set(), keepalive = 0,
                 address = None, groups = set(), logger = None):

        self.dev = dev
        self.pubkey = pubkey
        self.port = port
        self.endpoint = endpoint
        self.allowed_ips = allowed_ips
        self.keepalive = keepalive
        self.address = address
        self.groups = groups
        self.logger = logger or default_logger


    def __str__(self):

        o = "<Node: pubkey={}, endpoint={}".format(self.pubkey, self.endpoint)

        if VERBOSE:
            o += ", alowed_ips={}".format(",".join(self.allowed_ips))
            o += ", keepalive={}".format(self.keepalive)
            o += ", groups={}".format(" ".join(sorted(list(self.groups))))

        o += ">"

        return  o

    def format(self, indent = 4):
        lines = [
            "pubkey:      {}".format(self.pubkey),
            "dev:         {}".format(self.dev),
            "port:        {}".format(self.port),
            "endpoint:    {}".format(self.endpoint),
            "allowed_ips: {}".format(", ".join(self.allowed_ips)),
            "keepalive:   {}".format(self.keepalive),
            "address:     {}".format(self.address),
            "groups:      {}".format(", ".join(self.groups))
        ]
        return "\n".join(map(lambda x: " " * indent + x, lines))


    def update(self, key, value):

        changed = False

        if value == "None":
            value = None

        if key == "dev" and self.dev != value:
            changed = True
            self.dev = value
        elif key == "pubkey" and self.pubkey != value:
            changed = True
            self.pubkey = value
        elif key == "port" and self.port != int(value):
            changed = True
            self.port = int(value)
        elif key == "endpoint" and self.endpoint != value:
            changed = True
            self.endpoint = value
        elif key == "allowed_ips":
            if not value == "":
                ips = set(value.strip().replace(" ", "").split(","))
            else :
                ips = set()
            if self.allowed_ips != ips:
                changed = True
                self.allowed_ips = ips
        elif key == "keepalive" and self.keepalive != int(value):
            changed = True
            self.keepalive = int(value)
        elif key == "address" and self.address != value:
            changed = True
            self.address = value
        elif key == "groups":
            if not value == "":
                groups = set(value.strip().replace(" ", "").split(","))
            else:
                groups = set()
            if self.groups != groups:
                changed = True
                self.groups = groups

        return changed


    def deserialize(self, kvps):

        """ deserialize(self, kvps)
        @kvps: key value pairs: list of (key, value). Note that key includes
               etcd_id/etcd_prefix
        """
        # decode and strip key and value bytes to utf8 string
        kvs = []
        for key, value in kvps:
            key = key.decode("utf-8").split("/")[2]
            kvs.append((key, value.decode("utf-8")))

        # update parameters
        for k, v in kvs:
            self.update(k, v)


    def serialize_for_etcd(self, etcd_prefix, node_id):
        p = "{}/{}".format(etcd_prefix, node_id)

        return {
            p + "/dev": self.dev,
            p + "/pubkey": self.pubkey,
            p + "/port": str(self.port),
            p + "/endpoint": self.endpoint,
            p + "/allowed_ips": ",".join(self.allowed_ips),
            p + "/keepalive": str(self.keepalive),
            p + "/address": self.address,
            p + "/groups": ",".join(self.groups),
        }


    def install(self, wg_dev):

        if not self.pubkey:
            return

        cmds = []

        wgcmd = [ WGCMD, "set", wg_dev, "peer", self.pubkey ]
        if self.endpoint:
            wgcmd += [ "endpoint", self.endpoint ]
        if self.allowed_ips:
            wgcmd += [ "allowed-ips", ",".join(self.allowed_ips) ]
        if self.keepalive:
            wgcmd += [ "persistent-keepalive", str(self.keepalive) ]

        cmds.append(wgcmd)

        for cmd in cmds:
            subprocess.check_call(cmd)

        if self.logger:
            self.logger.debug("install node: %s",
                              ", ".join(map(lambda x: " ".join(x), cmds)))


    def uninstall(self, wg_dev):

        cmds = []

        wgcmd = [ WGCMD, "set", wg_dev, "peer", self.pubkey, "remove" ]
        cmds.append(wgcmd)

        for allowed_ip in self.allowed_ips:
            cmds.append([
                IPCMD, "route", "del", "to", allowed_ip,
            ])


        for cmd in cmds:
            subprocess.check_call(cmd)

        if self.logger:
            self.logger.debug("uninstall node: %s",
                              ", ".join(map(lambda x: " ".join(x), cmds)))
