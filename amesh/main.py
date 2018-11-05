#!/usr/bin/env python3

import os
import sys
import argparse
import configparser
import signal

if __name__ == "__main__":
    import amesh
else:
    from amesh import amesh



from logging import getLogger, DEBUG, INFO, StreamHandler, Formatter
from logging.handlers import SysLogHandler
logger = getLogger(__name__)
logger.setLevel(INFO)
stream = StreamHandler()
syslog = SysLogHandler(address = "/dev/log")
syslog.setFormatter(Formatter("amesh: %(message)s"))
logger.addHandler(stream)
logger.addHandler(syslog)
logger.propagate = False


def main():

    default_config_path = "/usr/local/etc/amesh/amesh.conf"

    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--debug", action = "store_true",
                        help = "enable debug logs")
    parser.add_argument("-c", "--config", type = argparse.FileType("r"),
                        default = default_config_path,
                        help = "amesh config file. default is " +
                        default_config_path)
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(DEBUG)

    config = configparser.ConfigParser()
    config.read_dict({
        "amesh": {
            "etcd_endpoint": "127.0.0.1:2379",
            "etcd_prefix": "amesh",
        },
        "wireguard": {
            "device": "None",
            "port": "51280",
            "address": "None",
            "pubkey_puth": "/usr/local/etc/amesh/public.key",
            "prvkey_path": "/usr/local/etc/amesh/private.key",
            "keepalive": "0",
        },
    })

    
    config.readfp(args.config)
    amesh_config = dict(config.items())["amesh"]
    wg_config = dict(config.items())["wireguard"]

    # Start Ameseh
    amesh_process = amesh.Amesh({
        "amesh": amesh_config,
        "wireguard": wg_config
    }, logger = logger)

    def sig_handler(signum, stack):
        amesh_process.cancel()
    signal.signal(signal.SIGINT, sig_handler)


    amesh_process.start()
    amesh_process.join()


if __name__ == "__main__":
    main()
