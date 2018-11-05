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

    def __init__(self, config_files):

        self.node_table = {} # key node_id, value = Node

        config = configparser.ConfigParser()
        config.read_dict({
            "amesh": {
                "etcd_endpoint": "127.0.0.1:2379",
                "etcd_prefix": "amesh",
            }
        })

        config_files = list(set(config_files))
        for config_file in config_files :
            config.read(config_file)

        self.etcd_endpoint = config["amesh"]["etcd_endpoint"]
        self.etcd_prefix = config["amesh"]["etcd_prefix"]

        logger.debug("etcd_endpoint: %s", self.etcd_endpoint)
        logger.debug("etcd_prefix:   %s", self.etcd_prefix)

        for section in config.sections():
            if section in ("amesh", "wireguard"):
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


    def get(self, args):

        etcd = self.etcd_client()

        if args.source == "etcd":
            node_table = {}
            for value, meta in etcd.get_prefix(self.etcd_prefix):
                _, node_id, key = meta.key.decode("utf-8").split("/")
                value = value.decode("utf-8")

                if not node_id in node_table:
                    node_table[node_id] = Node()

                node = node_table[node_id]
                node.update(key, value)

        elif args.source == "config":
            node_table = self.node_table

        for node_id in sorted(node_table.keys()):
            print("{}".format(node_id))
            print(node_table[node_id].format(indent = 4))
            print("")


    def put(self, args):

        etcd = self.etcd_client()
        put_nodes = []

        if args.sync:
            args.all_node = True

        # put nodes into etcd
        for node_id, node in self.node_table.items():

            if not args.all_node and not node_id in args.node_ids:
                continue

            put_nodes.append(node_id)

            d = node.serialize_for_etcd(self.etcd_prefix, node_id)
            for k, v in d.items():
                etcd.put(k, str(v))

        print("Put {} nodes. ({}).".format(len(put_nodes),
                                           " and ".join(sorted(put_nodes))))

        del_nodes = []

        if args.sync:
            # remove nodes they are not in config file

            for _, meta in etcd.get_prefix(self.etcd_prefix):
                _, node_id, _ = meta.key.decode("utf-8").split("/")
                if not node_id in self.node_table:
                    # this node is not in the config, so remove
                    del_nodes.append(node_id)
                    etcd.delete(meta.key.decode("utf-8"))

        del_nodes = sorted(list(set(del_nodes)))
        if del_nodes :
            print("Deleted {} nodes. ({}).".format(len(del_nodes),
                                                   " and ".join(del_nodes)))


    def delete(self, args):

        etcd = self.etcd_client()
        del_nodes = []

        if args.all_node:
            for node_id in self.node_table.keys():
                del_nodes.append(node_id)
                prefix = "{}/{}".format(self.etcd_prefix, node_id)
                ret = etcd.delete_prefix(prefix)
        else:
            for node_id in args.node_ids:
                del_nodes.append(node_id)
                prefix = "{}/{}".format(self.etcd_prefix, node_id)
                ret = etcd.delete_prefix(prefix)

        del_nodes = sorted(list(set(del_nodes)))

        print("Deleted {} nodes. ({}).".format(len(del_nodes),
                                               " and ".join(del_nodes)))


def main():

    default_config_path = "/usr/local/etc/amesh/amesh-control.conf"

    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--debug", action = "store_true",
                        help = "enable debug logs")
    parser.add_argument("-c", "--config",
                        default = [default_config_path],
                        action = "append",
                        help = "amesh control config file. " +
                        default_config_path + ". "
                        "multiple config files are allowed.")

    cmd_parsers = parser.add_subparsers(title = "subcommands",
                                        dest = "command")

    get_parser = cmd_parsers.add_parser("get", help = "get node information")
    get_parser.add_argument("source", choices = ["etcd", "config"],
                            default = "etcd", nargs = "?",
                            help = "data source")

    put_parser = cmd_parsers.add_parser("put", help = "put node information")
    put_parser.add_argument("node_ids", default = [], nargs = "*",
                            help = "node id list")
    put_parser.add_argument("-a", "--all-node", default = False,
                            action = "store_true",
                            help = "put all nodes in config file(s)")
    put_parser.add_argument("-s", "--sync", action = "store_true",
                            help = "remove nodes not in config file " +
                            "after putting all the nodes")

    del_parser = cmd_parsers.add_parser("delete", aliases = ["del"],
                                        help = "delete node")
    del_parser.add_argument("node_ids", default = [], nargs = "*",
                            help = "node id list")
    del_parser.add_argument("-a", "--all-node", default = False,
                            action = "store_true",
                            help = "delete all nodes in config file(s)")

    args = parser.parse_args()

    if args.debug:
        logger.setLevel(DEBUG)

    ac = AmeshControl(args.config)

    if args.command == "put":
        ac.put(args)
    elif args.command == "get":
        ac.get(args)
    elif args.command in ("delete", "del"):
        ac.delete(args)

if __name__ == "__main__":
    main()
