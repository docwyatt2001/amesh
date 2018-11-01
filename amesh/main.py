#!/usr/bin/env python3

import os
import sys
import argparse
import configparser

import amesh

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


if __name__ == "__main__" :

    parser = argparse.ArgumentParser()
    parser.add_argument("config", help = "amesh config file")
    args = parser.parse_args()

    config = configparser.ConfigParser()
    config.read_dict({
        "wireguard" : {
            "device" : "wg0",
            "port" : "5280",
            "prvkey_path" : "private.key",
            "keepalive" : "0",
        },
        "amesh" : {
            "etcd_endpoint" : "127.0.0.1:2379",
            "etcd_prefix" : "amesh",
        }
    })

    
    config.read(args.config)
    amesh_config = dict(config.items())["amesh"]
    wg_config = dict(config.items())["wireguard"]

    # Start Ameseh
    amesh = amesh.Amesh({
        "amesh" : amesh_config,
        "wireguard" : wg_config
    })


    amesh.init_wg_dev()
    amesh.etcd_watch()
