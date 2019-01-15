#!/usr/bin/env python3

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
syslog = SysLogHandler(address = "/dev/log")
syslog.setFormatter(Formatter("amesh: %(message)s"))
logger.addHandler(syslog)
logger.propagate = False


def main():

    default_config_path = "/usr/local/etc/amesh/amesh.conf"

    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--debug", action = "store_true",
                        help = "enable debug logs")
    parser.add_argument("-f", "--foreground-log", action = "store_true",
                        help = "enable foreground logs")
    parser.add_argument("-c", "--config", type = argparse.FileType("r"),
                        default = default_config_path,
                        help = "amesh config file. default is " +
                        default_config_path)
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(DEBUG)

    if args.foreground_log:
        stream = StreamHandler()
        logger.addHandler(stream)

    config = configparser.ConfigParser()
    config.readfp(args.config)
    etcd_config = dict((config.items()))["etcd"]
    amesh_config = dict(config.items())["amesh"]
    wg_config = dict(config.items())["wireguard"]

    # Start Ameseh
    amesh_process = amesh.Amesh({
        "etcd": etcd_config,
        "amesh": amesh_config,
        "wireguard": wg_config
    }, logger = logger)

    def sig_handler(signum, stack):
        amesh_process.cancel()
    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    amesh_process.start()
    amesh_process.join()
    # wait until amesh_process.cancel() is called by signal


if __name__ == "__main__":
    main()
