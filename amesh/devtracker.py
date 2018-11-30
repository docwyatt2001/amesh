


import re
import queue
import ipaddress
from pyroute2 import IPDB


from logging import getLogger, INFO, StreamHandler
from logging.handlers import SysLogHandler
default_logger = getLogger(__name__)
default_logger.setLevel(INFO)
stream = StreamHandler()
syslog = SysLogHandler(address = "/dev/log")
default_logger.addHandler(stream)
default_logger.addHandler(syslog)
default_logger.propagate = False


def whichipversion (addr) :

    if re.match (r'^(\d{1,3}\.){3,3}\d{1,3}$', addr)  :
        return 4

    if re.match (r'((([0-9a-f]{1,4}:){7}([0-9a-f]{1,4}|:))|(([0-9a-f]{1,4}:){6}(:[0-9a-f]{1,4}|((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3})|:))|(([0-9a-f]{1,4}:){5}(((:[0-9a-f]{1,4}){1,2})|:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3})|:))|(([0-9a-f]{1,4}:){4}(((:[0-9a-f]{1,4}){1,3})|((:[0-9a-f]{1,4})?:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:))|(([0-9a-f]{1,4}:){3}(((:[0-9a-f]{1,4}){1,4})|((:[0-9a-f]{1,4}){0,2}:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:))|(([0-9a-f]{1,4}:){2}(((:[0-9a-f]{1,4}){1,5})|((:[0-9a-f]{1,4}){0,3}:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:))|(([0-9a-f]{1,4}:){1}(((:[0-9a-f]{1,4}){1,6})|((:[0-9a-f]{1,4}){0,4}:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:))|(:(((:[0-9a-f]{1,4}){1,7})|((:[0-9a-f]{1,4}){0,5}:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:)))(%.+)?\s*$', addr) :
        return 6

    return -1



class DevTracker(object):

    def __init__(self, devlist, logger = None):
        self.devlist = devlist
        self.queue = queue.Queue()
        self.ipdb = IPDB()
        self.logger = logger or default_logger
        

    def _get_current(self):

        for dev in self.devlist:

            if not dev in self.ipdb.interfaces:
                continue

            devinfo = self.ipdb.by_name[dev]

            for addr, preflen in devinfo["ipaddr"]:
                if whichipversion(addr) == 4:
                    addr = "{}/{}".format(addr, preflen)
                    prefix = ipaddress.ip_interface(addr).network
                    msg = {
                        "action": "RTM_NEWADDR",
                        "device": dev,
                        "address": prefix,
                        }
                    self.queue.put(msg)


    def start(self):

        self.logger.debug("start to track devices: %s", " ".join(self.devlist))

        self._get_current()

        def ipdb_callback(ipdb, msg, action):
            
            if not action in ("RTM_NEWADDR", "RTM_DELADDR"):
                return

            if msg["family"] != 2:
                # XXX: IPv4 only :(
                return


            tracked_dev = None
            tracked_dev_addr = None
            for attr in msg["attrs"]:
                if attr[0] == "IFA_LABEL" and attr[1] in self.devlist:
                    tracked_dev = attr[1]
                elif attr[0] == "IFA_ADDRESS":
                    tracked_dev_addr = attr[1]

            if not tracked_dev or not tracked_dev_addr:
                return

            addr = "{}/{}".format(tracked_dev_addr, msg["prefixlen"])
            prefix = ipaddress.ip_interface(addr).network

            msg = {
                "action": action,
                "device": tracked_dev,
                "address": prefix,
            }

            try:
                self.logger.debug("device addr change: %s", str(msg))
                self.queue.put(msg)
            except queue.Full:
                self.logger.error("devtracker queue full for msg %s", str(msg))


        self.cbid = self.ipdb.register_callback(ipdb_callback)

        
    def stop(self):
        self.ipdb.unregister_callback(self.cbid)

    def queued(self):
        return (not self.queue.empty())

    def pop(self):
        try:
            return self.queue.get(block = False)
        except queue.Empty:
            return None
