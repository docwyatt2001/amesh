#!/usr/bin/env python3

import argparse
import configparser
import uuid
import etcd3

if __name__ == "__main__":
    from node import Node
else:
    from amesh.node import Node


from logging import getLogger, DEBUG, INFO, StreamHandler
from logging.handlers import SysLogHandler
logger = getLogger(__name__)
logger.setLevel(INFO)
stream = StreamHandler()
syslog = SysLogHandler(address = "/dev/log")
logger.addHandler(stream)
logger.addHandler(syslog)
logger.propagate = False



class AmeshControl(object):

    def __init__(self, config_file, remove = False):

        self.node_table = {} # key node_id, value = Node
        self.remove = remove

        config = configparser.ConfigParser()
        config.read_dict({
            "amesh": {
                "etcd_endpoint": "127.0.0.1:2379",
                "etcd_prefix": "amesh",
            }
        })

        config.read(config_file)

        self.etcd_endpoint = config["amesh"]["etcd_endpoint"]
        self.etcd_prefix = config["amesh"]["etcd_prefix"]

        logger.debug("etcd_endpoint: %s", self.etcd_endpoint)
        logger.debug("etcd_prefix:   %s", self.etcd_prefix)

        for section in config.sections():
            if section == "amesh":
                continue

            if (not "node_id" in config[section] and
                not "pubkey" in config[section]):
                err = "node_id or pubkey is reuqired in [{}]".format(section)

                logger.error(err)
                raise RuntimeError(err)

            if "node_id" in config[section]:
                node_id = config[section]["node_id"]
            else:
                pubkey = config[section]["pubkey"]
                node_id = str(uuid.uuid3(uuid.NAMESPACE_DNS, pubkey))

            node = Node(logger = logger)
            for key, value in config[section].items():
                node.update(key, value)

            self.node_table[node_id] = node
            logger.debug(node)


    def etcd_client(self):
        host, port = self.etcd_endpoint.split(":")
        return etcd3.client(host = host, port = port)


    def put(self):

        etcd = self.etcd_client()

        # put nodes into etcd
        for node_id, node in self.node_table.items():
            d = node.serialize_for_etcd(self.etcd_prefix, node_id)
            for k, v in d.items():
                etcd.put(k, v)

        if self.remove:
            # remove nodes they are not in config file

            for _, meta in etcd.get_prefix(self.etcd_prefix):
                _, node_id, _ = meta.key.decode("utf-8").split("/")
                if not node_id in self.node_table:
                    # this node is not in the config, so remove
                    etcd.delete(meta.key.decode("utf-8"))

    def get(self):

        etcd = self.etcd_client()
        node_table = {}

        for value, meta in etcd.get_prefix(self.etcd_prefix):
            _, node_id, key = meta.key.decode("utf-8").split("/")
            value = value.decode("utf-8")

            if not node_id in node_table:
                node_table[node_id] = Node()

            node = node_table[node_id]
            node.update(key, value)

        for node_id in sorted(node_table.keys()):
            print("{}".format(node_id))
            print(node_table[node_id].format(indent = 4))
            print("")


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--debug", action = "store_true",
                        help = "enable debug logs")
    parser.add_argument("-r", "--remove", action = "store_true",
                        help = "remove nodes not in config file")
    parser.add_argument("config", help = "amesh control config file")
    parser.add_argument("command", choices = ["put", "get", "update"],
                        nargs = '?', help = "command")
    #XXX: make command uses subparser
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(DEBUG)

    try:
        f = open(args.config, "r")
        f.close()
    except Exception as e:
        err = "failed to read {}: {}".format(args.config, e)
        logger.error(err)
        raise RuntimeError(err)

    ac = AmeshControl(args.config, remove = args.remove)

    if args.command == "put":
        ac.put()
    elif args.command == "get":
        ac.get()


if __name__ == "__main__":
    main()
