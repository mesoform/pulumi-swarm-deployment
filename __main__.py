"""A Google Cloud Python Pulumi program"""

import requests
import pulumi
import pulumi_gcp as gcp

current_ip = requests.get("https://ifconfig.me/ip").text.strip()
default_compute_sa = gcp.compute.get_default_service_account()
config = pulumi.Config()


class SwarmNetwork(pulumi.ComponentResource):
    def __init__(self, name: str, region: str, ssh_ips: list[str], service_ports: list[str], **kwargs):
        super().__init__('pkg:swarm:SwarmNetwork', name, None, opts=None)
        component_opts = pulumi.ResourceOptions(parent=self)
        network = gcp.compute.Network("swarm-network",
                                      auto_create_subnetworks=False,
                                      opts=component_opts)
        instance_subnet = gcp.compute.Subnetwork(f"{name}-instance-subnet",
                                                 region=region,
                                                 network=network.id,
                                                 ip_cidr_range="10.0.0.0/24",
                                                 opts=component_opts)
        docker_firewall = gcp.compute.Firewall(
            f"{name}-docker-firewall",
            network=network.self_link,
            allows=[{
                'protocol': 'tcp',
                'ports': ['2376', '2377', '7946']
            },
            {
                'protocol': 'udp',
                'ports': ['4789', '7946']
            }],
            # source_ranges=[f"{instance_subnet.ip_cidr_range}/32"],
            source_ranges=[instance_subnet.ip_cidr_range],
            opts=component_opts
        )
        ssh_firewall = gcp.compute.Firewall(
            f"{name}-ssh-firewall",
            network=network.self_link,
            allows=[{"protocol": "tcp", "ports": ["22"]}],
            source_ranges=[f'{ip}/32' for ip in ssh_ips],
            opts=component_opts
        )
        service_firewall = gcp.compute.Firewall(
            f"{name}-service-firewall",
            network=network.self_link,
            allows=[{"protocol": "tcp", "ports": service_ports}],
            source_ranges=[f'{ip}/32' for ip in ssh_ips] + [f"{current_ip}/32", instance_subnet.ip_cidr_range],
            opts=component_opts
        )
        self.network_id = network.id
        self.instance_subnet_id = instance_subnet.id
        self.firewall_rules = [docker_firewall.id, ssh_firewall.id, service_firewall.id]


def get_latest_ubuntu_image(version):
    latest_ubuntu_image = gcp.compute.get_image(
        family=f"ubuntu-{version.replace('.', '')}-lts", project="ubuntu-os-cloud"
    )
    return latest_ubuntu_image.self_link


class SwarmCluster(pulumi.ComponentResource):
    def __init__(self, name: str, instance_type: str, nodes: int, subnet_id: pulumi.Output[str], region: str,
                 ssh_pub_keys: dict[str, str], compute_sa: str, docker_token_secret_name: str, **kwargs):
        super().__init__('pkg:swarm:SwarmInstance', name, None, opts=None)
        component_opts = pulumi.ResourceOptions(parent=self)
        self.ssh_keys_string = "\n".join([username + ":" + pub_key for username, pub_key in ssh_pub_keys.items()])
        initial_instance = gcp.compute.Instance(
            f"{name}-swarm-node-0",
            zone=f"{region}-a",
            service_account=gcp.compute.InstanceServiceAccountArgs(email=compute_sa, scopes=["cloud-platform"]),
            machine_type=instance_type,
            boot_disk={
                "initialize_params": {
                    "image": get_latest_ubuntu_image("20.04")
                }
            },
            metadata_startup_script=f"""apt update && apt upgrade -y && apt -y install docker.io && docker swarm init && docker swarm join-token manager -q | gcloud secrets versions add {docker_token_secret_name} --data-file=-""",
            network_interfaces=[{"subnetwork": subnet_id, "access_configs": [{}]}],
            metadata={"ssh-keys": self.ssh_keys_string},
            opts=component_opts
        )
        instance_template = gcp.compute.InstanceTemplate(
            f"{name}-swarm-node-template",
            name_prefix=f"{name}-swarm-cluster",
            region=region,
            machine_type=instance_type,
            service_account=gcp.compute.InstanceTemplateServiceAccountArgs(email=compute_sa, scopes=["cloud-platform"]),
            disks=[gcp.compute.InstanceTemplateDiskArgs(
                source_image=get_latest_ubuntu_image("22.04")
            )],
            metadata_startup_script=initial_instance.network_interfaces[0].network_ip.apply(
                lambda private_ip: f"""apt update && apt upgrade -y && apt -y install docker.io && docker swarm join --token $(gcloud secrets versions access latest --secret={docker_token_secret_name}) {private_ip}:2377"""),
            network_interfaces=[{"subnetwork": subnet_id, "access_configs": [{}]}],
            metadata={"ssh-keys": self.ssh_keys_string},
            opts=pulumi.ResourceOptions(parent=self, depends_on=initial_instance)
        )
        self.swarm_nodes = [initial_instance]
        zones = ["a", "b", "c"]
        for i in range(1, nodes):
            swarm_node = gcp.compute.InstanceFromTemplate(f"{name}-swarm-node-{i}",
                                                          zone=f"{region}-{zones[i]}",
                                                          source_instance_template=instance_template.self_link_unique,
                                                          opts=pulumi.ResourceOptions(parent=self))
            self.swarm_nodes.append(swarm_node)


args = {
    "name": config.require("name"),
    "docker_token_secret_name": config.require("docker_token_secret_name"),
    "region": config.get("region") or "europe-west2",
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
