

import ipaddress

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
                 pubkey = None, endpoint = None, allowed_ips = set(),
                 keepalive = 0, groups = set(), logger = None):

        self.pubkey = pubkey
        self.endpoint = endpoint
        self.allowed_ips = allowed_ips
        self.keepalive = keepalive
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
            "endpoint:    {}".format(self.endpoint),
            "allowed_ips: {}".format(", ".join(self.allowed_ips)),
            "keepalive:   {}".format(self.keepalive),
            "groups:      {}".format(", ".join(self.groups))
        ]
        return "\n".join(map(lambda x: " " * indent + x, lines))


    def update(self, key, value):

        changed = False

        if value == "None":
            value = None

        if key == "pubkey" and self.pubkey != value:
            if not value :
                # delete case
                changed = True
                self.pubkey = None
            else:
                changed = True
                self.pubkey = value

        elif key == "endpoint" and self.endpoint != value:
            changed = True
            self.endpoint = value

        elif key == "allowed_ips":
            if not value == "":
                try:
                    prefixes = map(ipaddress.ip_network,
                                   value.strip().replace(" ", "").split(","))
                    ips = set(prefixes)
                except Exception as e:
                    self.logger.error("failed to parse allowed_ips: %s, %s",
                                      value, e)
                    return changed
            else :
                ips = set()
            if self.allowed_ips != ips:
                changed = True
                self.allowed_ips = ips

        elif key == "keepalive" and self.keepalive != int(value):
            changed = True
            self.keepalive = int(value)

        elif key == "groups":
            if not value == "":
                groups = set(value.strip().replace(" ", "").split(","))
            else:
                groups = set()
            if self.groups != groups:
                changed = True
                self.groups = groups

        return changed


    def add_allowed_ip(self, allowed_ip):
        self.allowed_ips.add(allowed_ip)

    def remove_allowed_ip(self, allowed_ip):
        if allowed_ip in self.allowed_ips:
            self.allowed_ips.remove(allowed_ip)

    def serialize_for_etcd(self, etcd_prefix, node_id):
        p = "{}/{}".format(etcd_prefix, node_id)

        return {
            p + "/pubkey": self.pubkey,
            p + "/endpoint": str(self.endpoint),
            p + "/allowed_ips": ",".join(map(str, self.allowed_ips)),
            p + "/keepalive": str(self.keepalive),
            p + "/groups": ",".join(self.groups),
        }


