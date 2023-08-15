import pulumi
import pulumi_gcp as gcp
import socket
import time


class SwarmNetwork(pulumi.ComponentResource):
    def __init__(self, name: str, region: str, ssh_ips: list[str], service_ports: list[str], subnet_cidr_range: str,
                 **kwargs):
        super().__init__('pkg:swarm:SwarmNetwork', f"{name}-network-infrastructure", None, opts=None)
        docker_cidr_range = "172.17.0.0/16"
        component_opts = pulumi.ResourceOptions(parent=self)
        network = gcp.compute.Network(f"{name}-swarm-network",
                                      auto_create_subnetworks=False,
                                      opts=component_opts)
        instance_subnet = gcp.compute.Subnetwork(f"{name}-instance-subnet",
                                                 region=region,
                                                 network=network.id,
                                                 ip_cidr_range=subnet_cidr_range,
                                                 secondary_ip_ranges=[gcp.compute.SubnetworkSecondaryIpRangeArgs(
                                                     range_name="docker",
                                                     ip_cidr_range=docker_cidr_range
                                                 )],
                                                 opts=component_opts)
        swarm_firewall = gcp.compute.Firewall(
            f"{name}-swarm-internal-firewall",
            network=network.self_link,
            allows=[{'protocol': 'tcp'},
                    {'protocol': 'icmp'},
                    {
                        'protocol': 'udp',
                        'ports': ['4789', '7946']
                    }],
            source_ranges=[subnet_cidr_range, docker_cidr_range],
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
            source_ranges=[f'{ip}/32' for ip in ssh_ips],
            opts=component_opts
        )
        self.network_id = network.id
        self.instance_subnet_id = instance_subnet.id
        self.firewall_rules = [swarm_firewall.id, ssh_firewall.id, service_firewall.id]


def get_latest_ubuntu_image(version):
    latest_ubuntu_image = gcp.compute.get_image(
        family=f"ubuntu-{version.replace('.', '')}-lts", project="ubuntu-os-cloud"
    )
    return latest_ubuntu_image.self_link


class SwarmCluster(pulumi.ComponentResource):
    def __init__(self, name: str, instance_type: str, nodes: int, subnet_id: pulumi.Output[str], region: str,
                 ssh_pub_keys: dict[str, str], compute_sa: str, docker_token_secret_name: str, **kwargs):
        super().__init__('pkg:swarm:SwarmCluster', f"{name}-swarm-cluster", None, opts=None)
        component_opts = pulumi.ResourceOptions(parent=self)
        add_docker_users = f'for user in {" ".join(ssh_pub_keys.keys())}; do sudo usermod -a -G docker "$user"; done'
        startup_script = """
apt update && apt -y install docker.io 
{swarm_setup}
{add_docker_users}
"""
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
            metadata_startup_script=startup_script.format(
                swarm_setup=f"docker swarm init && docker swarm join-token manager -q | gcloud secrets versions add {docker_token_secret_name} --data-file=-",
                add_docker_users=add_docker_users),
            network_interfaces=[{"subnetwork": subnet_id, "access_configs": [{}]}],
            metadata={"ssh-keys": self.ssh_keys_string},
            opts=component_opts
        )
        self.initial_instance_private_ip: pulumi.Output[str] = initial_instance.network_interfaces[0].network_ip

        # test = pulumi.Output.apply(self._check_manager_running(initial_instance.id))
        while not self._check_manager_running():
            pulumi.log.debug("Waiting for initial instance to be ready")
            time.sleep(10)

        instance_template = gcp.compute.InstanceTemplate(
            f"{name}-swarm-node-template",
            name_prefix=f"{name}-swarm-cluster",
            region=region,
            machine_type=instance_type,
            service_account=gcp.compute.InstanceTemplateServiceAccountArgs(email=compute_sa, scopes=["cloud-platform"]),
            disks=[gcp.compute.InstanceTemplateDiskArgs(
                source_image=get_latest_ubuntu_image("22.04")
            )],
            metadata_startup_script=self.initial_instance_private_ip.apply(
                lambda
                    private_ip: startup_script.format(
                    swarm_setup=f"apt update && apt -y install docker.io && docker swarm join --token $(gcloud secrets versions access latest --secret={docker_token_secret_name}) {private_ip}:2377",
                    add_docker_users=add_docker_users)),
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

    def _check_manager_running(self) -> pulumi.Output[bool]:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        return self.initial_instance_private_ip.apply(lambda ip: sock.connect_ex((ip, 22)) == 0)
