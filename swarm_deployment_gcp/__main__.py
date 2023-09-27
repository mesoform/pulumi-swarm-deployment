"""A Google Cloud Python Pulumi program"""

import pulumi
from swarm import SwarmDeploymentGCP, SwarmDeploymentGCPArgs


config = pulumi.Config()


def main():
    config_args = {
        "name": config.require("name"),
        "docker_token_secret_name": config.require("docker_token_secret_name"),
        "docker_token_secret_user_managed": config.get_bool("docker_token_secret_user_managed"),
        "region": config.get("region"),
        "subnet_cidr_range": config.get("subnet_cidr_range"),
        "ssh_pub_keys": config.get_object("ssh_pub_keys"),
        "include_current_ip": config.get_bool("include_current_ip"),
        "allowed_ips": config.get_object("allowed_ips"),
        "compute_sa": config.get("compute_sa"),
        "service_ports": config.get_object("service_ports"),
        "machine_type": config.get("machine_type"),
        "instance_image_id": config.get("instance_image_id"),
        "instance_count": config.get_int("instance_count"),
        "generate_ssh_key": config.get("generate_ssh_key"),
        "generated_ssh_key_path": config.get("generated_ssh_key_path")
    }
    swarm_deployment = SwarmDeploymentGCP(SwarmDeploymentGCPArgs(**config_args))


if __name__ == '__main__':
    main()


