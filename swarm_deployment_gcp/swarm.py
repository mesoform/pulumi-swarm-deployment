"""Pulumi module to deploy GCP swarm cluster
"""
import pulumi
import pulumi_gcp as gcp
import socket
import time
import os
import requests
from cryptography.hazmat.primitives import serialization as crypto_serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend as crypto_default_backend


class SwarmDeploymentGCPArgs:
    """
    Class to represent configuration arguments for SwarmDeploymentGCP
    Attributes:
        name (str): Name of the target application the cluster deployment is for
        docker_token_secret_name (str): Secret name in Google Secret Manager for swarm manager token storage
        region (str): Deployment region for resources
        subnet_cidr_range (str): CIDR range for subnet
        ssh_pub_keys (dict[str, str]) :SSH keys to add to instances with format 'username: public-ssh-key'.
        allowed_ips (list[str]): IPs with SSH access to instances and access to docker service ports
        compute_sa (str): Service account used by the compute instances (must have access to docker token secret).
            Uses default compute service account by default
        service_ports (list[str]): Docker service ports accessible by specified ips
        machine_type (str): Compute instance machine type, defaults to "e2-micro"
        instance_image_id (str): Compute instance image id, with the format {project}/{family}, or {project}/{family}.
            Defaults to ubuntu-os-cloud/ubuntu-2204-lts
        instance_count (int): Number of compute instances to have in the swarm
        generated_ssh_key_path (str): Storage path for the generated ssh key file.

    """
    def __init__(self,
                 name: str,
                 docker_token_secret_name: str,
                 region: str,
                 subnet_cidr_range: str,
                 ssh_pub_keys: dict[str, str],
                 include_current_ip: bool,
                 allowed_ips: list[str],
                 compute_sa: str,
                 service_ports: list[str],
                 machine_type: str,
                 instance_image_id: str,
                 instance_count: int,
                 generated_ssh_key_path: str):
        """

        :param name: Prefix for deployed resources
        :param docker_token_secret_name: Secret name in Google Secret Manager for swarm manager token storage
        :param region: Deployment region for resources
        :param subnet_cidr_range: CIDR range for subnet
        :param ssh_pub_keys:SSH keys to add to instances with format 'username: public-ssh-key'.
        :param include_current_ip: Whether to include the current deployers IP in allowed_ips
        :param allowed_ips: IPs with SSH access to instances and access to docker service ports
        :param compute_sa: Service account used by the compute instances (must have access to docker token secret).
            Uses default compute service account by default
        :param service_ports: Docker service ports accessible by specified ips
        :param machine_type: Compute instance machine type, defaults to "e2-micro"
        :param instance_image_id: Compute instance image id, with the format {project}/{family}, or {project}/{family}.
            Defaults to ubuntu-os-cloud/ubuntu-2204-lts
        :param instance_count: Number of compute instances to have in the swarm
        :param generated_ssh_key_path: Storage path for the generated ssh key file.
        """
        default_compute_sa = gcp.compute.get_default_service_account().email
        self.name = name
        self.docker_token_secret_name = docker_token_secret_name
        self.region = region or "europe-west2"
        self.subnet_cidr_range = subnet_cidr_range or "10.0.0.0/24"
        self.ssh_pub_keys = ssh_pub_keys or {}
        self.allowed_ips = allowed_ips or []
        if include_current_ip:
            current_ip = requests.get("https://ifconfig.me/ip").text.strip()
            self.allowed_ips = self.allowed_ips + [current_ip]
        self.compute_sa = compute_sa or default_compute_sa
        self.service_ports = service_ports or []
        self.machine_type = machine_type or "e2-micro"
        self.instance_image_id = instance_image_id or "ubuntu-os-cloud/ubuntu-2204-lts"
        self.instance_count = instance_count or 3
        self.generated_ssh_key_path = generated_ssh_key_path or "./deployer_ssh_key"


class SwarmDeploymentGCP(pulumi.ComponentResource):
    """
    Class to deploy network, compute instances, and initialize Docker Swarm cluster.

    Uses SwarmNetwork to set up necessary network infrastructure and SwarmCluster
    to create a cluster within that network.

    Attributes:
        args (SwarmDeploymentGCPArgs): Configuration arguments
        swarm_network (SwarmNetwork): Network Infrastucture for the swarm cluster
        swarm_cluster (SwarmCluster): Computes instances comprising Docker Swarm cluster
    """
    def __init__(self, args: SwarmDeploymentGCPArgs):
        super().__init__('pkg:deployment:ClusterStackDeployment', args.name, None, opts=None)
        # deployment_ssh_key = PrivateKey("deployer", algorithm="RSA", rsa_bits=4096,
        #                                 opts=pulumi.ResourceOptions(
        #                                     additional_secret_outputs=['private_key_openssh', 'private_key_pem']))
        self.args = args
        pulumi.log.info(f"{vars(self.args)}")
        self.swarm_network = SwarmNetwork(opts=pulumi.ResourceOptions(parent=self), **vars(args))
        deployer_ssh_key_public = self.create_ssh_keypair()
        args.ssh_pub_keys['deployer'] = deployer_ssh_key_public
        pulumi.log.info(f"ssh_keys: {args.ssh_pub_keys}")
        self.swarm_cluster = SwarmCluster(subnet_id=self.swarm_network.instance_subnet_id,
                                          opts=pulumi.ResourceOptions(parent=self), **vars(args))
        # pulumi.export("ssh_keys", args.ssh_pub_keys)
        for i, instance in enumerate(self.swarm_cluster.swarm_nodes):
            pulumi.export(f"instance-{i}-name", instance.name)
            pulumi.export(f"instance-{i}-external_ip", instance.network_interfaces[0]["access_configs"][0].nat_ip)

    def create_ssh_keypair(self) -> str:
        """
        Generate an ssh keypair

        Saves the private key at the location specified by `generate_ssh_key_path`,
        adds it to the ssh agent using `ssh-add`, and returns the public key.

        :return: Public key of generated SSH key pair
        """
        key = rsa.generate_private_key(
            backend=crypto_default_backend(),
            public_exponent=65537,  # Standard for RSA, part of public key
            key_size=4096
        )
        private_key = key.private_bytes(
            crypto_serialization.Encoding.PEM,
            crypto_serialization.PrivateFormat.PKCS8,
            crypto_serialization.NoEncryption())
        public_key = key.public_key().public_bytes(
            crypto_serialization.Encoding.OpenSSH,
            crypto_serialization.PublicFormat.OpenSSH).decode("utf-8")

        with open(self.args.generated_ssh_key_path, 'wb') as f:
            f.write(private_key)
        os.chmod(self.args.generated_ssh_key_path, 0o600)
        os.system(f"ssh-add {self.args.generated_ssh_key_path}")
        return public_key


class SwarmNetwork(pulumi.ComponentResource):
    """
    Class to set up Network, Subnet, and Firewall Rules for Swarm Cluster

    Attributes:
        network_id (str): Google VPC network ID
        instance_subnet_id (str): ID of the network's subnet to be used by Compute Instances
        firewall_rules (list[str]): List of creatd firewall rule IDs
    """
    def __init__(self, name: str, region: str, allowed_ips: list[str], service_ports: list[str], subnet_cidr_range: str,
                 opts=None, **kwargs):
        """

        :param name: Prefix for deployed resources
        :param region: Region for subnet
        :param allowed_ips: IPs that can access SSH and service ports
        :param service_ports: Ports to be exposed for use by services
        :param subnet_cidr_range: CIDR range for subnet
        :param opts: Pulumi options
        """
        super().__init__('pkg:swarm:SwarmNetwork', f"{name}-network-infrastructure", None, opts=opts)
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
            source_ranges=[f'{ip}/32' for ip in allowed_ips],
            opts=component_opts
        )
        service_firewall = gcp.compute.Firewall(
            f"{name}-service-firewall",
            network=network.self_link,
            allows=[{"protocol": "tcp", "ports": service_ports}],
            source_ranges=[f'{ip}/32' for ip in allowed_ips],
            opts=component_opts
        )
        self.register_outputs({
            "network_id": network.id,
            "instance_subnet_id": instance_subnet.id,
            "firewall_rule_ids": {
                "swarm_firewall": swarm_firewall.id,
                "ssh_firewall": ssh_firewall.id,
                "service_firewall": service_firewall.id
            }
        })
        self.network_id = network.id
        self.instance_subnet_id = instance_subnet.id
        self.firewall_rules = [swarm_firewall.id, ssh_firewall.id, service_firewall.id]


class SwarmCluster(pulumi.ComponentResource):
    """
    Creates specified number of compute instances and initializes a Docker Swarm cluster.

    - The first instance is created and initialized as the Docker Swarm manager node.
    - The Docker join token of the manager is saved to Google Secret Manager.
    - An instance template for manager nodes is created using the token.
    - The remaining instances are created using this template.

    Attributes:
        initial_instance_private_ip (pulumi.Output[str]): Private IP of the initial instance.
        swarm_nodes (list): List of all swarm nodes including the initial instance.
    """
    def __init__(self, name: str, machine_type: str, instance_count: int, subnet_id: pulumi.Output[str], region: str,
                 ssh_pub_keys: pulumi.Output[dict[str, str]], compute_sa: str, docker_token_secret_name: str,
                 instance_image_id: str, opts=None, **kwargs):
        """

        :param name: Name prefix for the resources
        :param machine_type: The machine type for the compute instances
        :param instance_count: Total number of compute instances to be in swarm
        :param subnet_id: ID of the subnet instances are in
        :param region: Region for instances to be in
        :param ssh_pub_keys: SSH keys to add to instances with format 'username: public-ssh-key'.
        :param compute_sa: Service account to be used by compute instances (requires access to docker_token_secret_name secret)
        :param docker_token_secret_name: Name of secret for storing docker join token (must be within current project)
        :param instance_image_id: Compute instance image id, with the format {project}/{family}, or {project}/{family}.
        :param opts: Pulumi options
        """
        super().__init__('pkg:swarm:SwarmCluster', f"{name}-swarm-cluster", None, opts=opts)
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
            machine_type=machine_type,
            boot_disk={
                "initialize_params": {
                    "image": instance_image_id
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
        retry = 0
        while retry < 30 and not self._check_manager_running() :
            pulumi.log.debug("Waiting for initial instance to be ready")
            time.sleep(10)
            retry += 1

        instance_template = gcp.compute.InstanceTemplate(
            f"{name}-swarm-node-template",
            name_prefix=f"{name}-swarm-node",
            region=region,
            machine_type=machine_type,
            service_account=gcp.compute.InstanceTemplateServiceAccountArgs(email=compute_sa, scopes=["cloud-platform"]),
            disks=[gcp.compute.InstanceTemplateDiskArgs(
                source_image=instance_image_id
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
        for i in range(1, instance_count):

            swarm_node = gcp.compute.InstanceFromTemplate(f"{name}-swarm-node-{i}",
                                                          zone=f"{region}-{zones[i % len(zones)]}",
                                                          source_instance_template=instance_template.self_link_unique,
                                                          opts=pulumi.ResourceOptions(parent=self))
            self.swarm_nodes.append(swarm_node)
        self.register_outputs({
            "swarm_nodes": self.swarm_nodes
        })

    def _check_manager_running(self) -> pulumi.Output[bool]:
        """
        Check if the initial compute instance is running by attempting an SSH connection.

        This method tries to establish a connection to the SSH port (port 22) of the instance using its private IP.
        If the connection is successful (port 22 is open and reachable), the instance is assumed to be running.

        :return: True if the SSH port is open and reachable; otherwise False.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        return self.initial_instance_private_ip.apply(lambda ip: sock.connect_ex((ip, 22)) == 0)
