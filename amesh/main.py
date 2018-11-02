

import os
import sys
import argparse
import configparser
import signal

from amesh import amesh

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


def main() :

    parser = argparse.ArgumentParser()
    parser.add_argument("config", help = "amesh config file")
    args = parser.parse_args()

    config = configparser.ConfigParser()
    config.read_dict({
        "amesh" : {
            "etcd_endpoint" : "127.0.0.1:2379",
            "etcd_prefix" : "amesh",
        },
        "wireguard" : {
            "device" : "wg0",
            "port" : "5280",
            "prvkey_path" : "private.key",
            "keepalive" : "0",
        },
    })

    
    if not os.path.exists(args.config) :
        logger.error("config file {} does not exist".format(args.config))
        sys.exit(1)

    config.read(args.config)
    amesh_config = dict(config.items())["amesh"]
    wg_config = dict(config.items())["wireguard"]

    # Start Ameseh
    amesh_process = amesh.Amesh({
        "amesh" : amesh_config,
        "wireguard" : wg_config
    })

    def sig_handler(signum, stack) :
        amesh_process.cancel()
    signal.signal(signal.SIGINT, sig_handler)


    amesh_process.start()
    amesh_process.join()


if __name__ == "__main__" :
    main()
