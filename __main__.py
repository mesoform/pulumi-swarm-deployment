"""A Google Cloud Python Pulumi program"""

import requests
import pulumi
from swarm import SwarmCluster, SwarmNetwork
import pulumi_gcp as gcp


config = pulumi.Config()

current_ip = requests.get("https://ifconfig.me/ip").text.strip()

default_compute_sa = gcp.compute.get_default_service_account()

args = {
    "name": config.require("name"),
    "docker_token_secret_name": config.require("docker_token_secret_name"),
    "region": config.get("region") or "europe-west2",
    "subnet_cidr_range": config.get("subnet_cidr_range") or "10.0.0.0/24",
    "ssh_pub_keys": config.get_object("ssh_pub_keys") or {},
    "ssh_ips": [current_ip] + (config.get_object("ssh_ips") or []),
    "compute_sa": config.get("compute_sa") or default_compute_sa,
    "service_ports": config.get_object("service_ports") or [],
    "instance_type": config.get("instance_type") or "e2-micro",
    "nodes": config.get_int("nodes") or 3

}

pulumi.log.info(f"args: {args}")

swarm_network = SwarmNetwork(**args)
swarm_cluster = SwarmCluster(subnet_id=swarm_network.instance_subnet_id, **args)

for i, instance in enumerate(swarm_cluster.swarm_nodes):
    pulumi.export(f"instance-{i}-name", instance.name)
    pulumi.export(f"instance-{i}-external_ip", instance.network_interfaces[0]["access_configs"][0].nat_ip)

