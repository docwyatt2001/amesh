#!/usr/bin/env python3

import argparse
import configparser
import uuid
import etcd3

if __name__ == "__main__" :
    from node import Node
else :
    from amesh.node import Node


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



class AmeshControl(object) :

    def __init__(self, config_file, remove = False) :

        self.node_table = {} # key node_id, value = Node
        self.remove = remove

        config = configparser.ConfigParser()
        config.read_dict({
            "amesh": {
                "etcd_endpoint" : "127.0.0.1:2379",
                "etcd_prefix" : "amesh",
            }
        })

        config.read(config_file)

        self.etcd_endpoint = config["amesh"]["etcd_endpoint"]
        self.etcd_prefix = config["amesh"]["etcd_prefix"]
    
        logger.debug("etcd_endpoint: {}".format(self.etcd_endpoint))
        logger.debug("etcd_prefix:   {}".format(self.etcd_prefix))

        for section in config.sections() :
            if section == "amesh" :
                continue

            if (not "node_id" in config[section] or
                not "pubkey" in config[section]) :
                err = "node_id or pubkey is reuqired in [{}]".format(section)
                
                logger.error(err)
                raise RuntimeError(err)
                
            if "node_id" in config[section] :
                node_id = config[section]["node_id"]
            else :
                pubkey = config[section]["pubkey"]
                node_id = str(uuid.uuid3(uuid.NAMESPACE_DNS, pubkey))

            node = Node(logger = logger)
            for key, value in config[section].items() :
                node.update(key, value)

            self.node_table[node_id] = node
            logger.debug(node)


    def etcd_client(self) :
        host, port = self.etcd_endpoint.split(":")
        return etcd3.client(host = host, port = port)


    def put(self) :
        
        etcd = self.etcd_client()

        # put nodes into etcd
        for node_id, node in self.node_table.items() :
            d = node.serialize_for_etcd(self.etcd_prefix, node_id)
            for k, v in d.items():
                etcd.put(k, v)
            
        if self.remove :
            # remove nodes they are not in config file

            for value, meta in etcd.get_prefix(self.etcd_prefix) :
                prefix, node_id, key = meta.key.decode("utf-8").split("/")
                if not node_id in self.node_table :
                    # this node is not in the config, so remove
                    etcd.delete(meta.key.decode("utf-8"))



def main() :

    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--debug", action = "store_true",
                        help = "enable debug logs")
    parser.add_argument("-r", "--remove", action = "store_true",
                        help = "remove nodes in etcd not in config file")
    parser.add_argument("config", help = "amesh control config file")
    args = parser.parse_args()

    if args.debug :
        logger.setLevel(DEBUG)
        
    try :
        f = open(args.config, "r")
        f.close()
    except Exception as e:
        err = "failed to read {}: {}".format(args.config, e)
        logger.error(err)
        raise RuntimeError(err)

    ac = AmeshControl(args.config, remove = args.remove)
    ac.put()


if __name__ == "__main__" :
    main()
