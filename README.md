# Swarm Deployment

* [Summary](#Summary)
* [Description](#Description)
* [How To](#how-to-use-module)
* [About Us](#ABOUT-US)
    * [Contributing](#Contributing)
    * [License](#License)

## Summary
This repository defines Pulumi Component Resources for deploying compute instances and initialising a docker swarm.

## Description
### SSH Keys
For automated deployments, an SSH key is generated on the deploying device, and is added to the compute instance.
This allows the deployer to create a docker context to connect and deploy a stack to the swarm cluster.
This can be done by adding an ssh context from local machine, i.e. `docker context create test-swarm --docker "host=ssh://deployer@{instance-ip}"`

### Compute Instances
The program creates and manages compute instances on GCP. The first instance is initialized as the Docker Swarm manager node. 
Subsequent instances join the Swarm using a token saved in Google Secret Manager. Each instance:

- Is within the subnet created by the SwarmNetwork component. The instances are assigned different zones (a, b or c)
  based on the instance number (e.g. instance 0,3,6 etc. would be zone `a`, 1,4,7 etc. would be `b`, and 2,5,8 etc. would be `c`)
- Has docker installed and initialises/joins docker swarm node
- Has generated SSH key added so the deployer can easily interact with the cluster.

### Network Components
The following network components are created:

- The defined swarm network.
- A subnet with a specified CIDR range and a secondary range `172.17.0.0/16` for Docker communications.
- Firewall rules:
  - **Internal Swarm Communication:** Allows nodes in the Swarm to communicate with each other, accepting all tcp, udp, 
    icmp and esp connections between instances. 
  - **SSH Access:** Permits SSH access to the instances for specified IPs
  - **Service Access:** If any services are exposed on the nodes, this rule will ensure they're accessible.


## How to use module

This module can be used by either importing the module into a pulumi program, 
or by cloning and using this repository directly.

### Prerequisites
To use this module the following prerequisites must be met:
* Python version 3.10+ installed
* Pulumi version 3+
* Google APIs enabled:
  * Compute Engine
  * Secret Manager
* Service account to be used by compute instances (set by `compute_sa`), with `roles/secretmanager.admin` 
to create and access the secrets for swarm initialisation


### Import module

1. Create a pulumi program
2. Include this module in requirements.txt (e.g. `swarm-deployment @ git+https://github.com/mesoform/pulumi-swarm-deployment.git`)
3. Use Component resources in code (see example)

### Cloning
1. Clone this repository.
2. Navigate to the directory containing the Pulumi program.
3. Modify the configuration for the stack
4. Run `pulumi up`. Review the proposed changes and confirm the deployment.

### Configuration
Both importing and cloning methods require configuration of `pulumi.<stack-name>.yml`.
The values can either be configured by setting up the file directly or using the `pulumi config` command.

The required values to be set are:
*  `gcp:project`: The Google project where the resources will be deployed
*  `<pulumi-program-name>:docker_token_secret_name`: The name that the secret holding the docker token should have
*  `<pulumi-program-name>:name`: Name for the cluster, i.e. the prefix for all resources deployed 

Note `pulumi-program-name` refers to the `name` value in `Pulumi.yaml`, so if cloning this repo that would be "swarm-deployment-gcp".  

Remaining configuration values are:
*  `region`: Deployment region for resources (default: `"europe-west2"`)
*  `subnet_cidr_range`: CIDR range for subnet (default: `"10.0.0.0/16"`)
*  `ssh_pub_keys`:SSH keys to add to instances with format 'username: public-ssh-key' (default: Map containing generated "deployer" ssh key)
*  `include_current_ip`: Whether to include the current deployers IP in `allowed_ips` for ssh access to instances (default: true)
*  `allowed_ips`: IPs with SSH access to instances and access to docker service ports 
(default: Empty list, unless `include_current_ip` is true, where the list will contain the IP of the deployer)
*  `compute_sa`: Service account used by the compute instances. Note this service account must have access to docker token secret
(default: uses default compute service account)
*  `service_ports`: Docker service ports accessible by specified ips (default: `[]`)
*  `machine_type`: Compute instance machine type, (default: `"e2-micro"`)
*  `instance_image_id`: Compute instance image id, with the format `"{project}/{image}"`, or `"{project}/{family}"` 
(default: `"ubuntu-os-cloud/ubuntu-2204-lts"`)
*  `instance_count`: Number of compute instances to have in the swarm (default: `3`)
*  `generate_ssh_key`: Whether to generate `deployer` ssh key to allow access to instance (default `false`)
*  `generated_ssh_key_path`: Storage path for the generated ssh private key file (default `"./deployer_ssh_key"`)


## Examples
### main.py
```python
"""A Google Cloud Python Pulumi program"""

import pulumi
from swarm_deployment_gcp import SwarmDeploymentGCP, SwarmDeploymentGCPArgs

config = pulumi.Config()

config_args = {
    "name": config.require("name"),
    "docker_token_secret_name": config.require("docker_token_secret_name"),
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
    "generated_ssh_key_path": config.get("generated_ssh_key_path")
}

deployment = SwarmDeploymentGCP(SwarmDeploymentGCPArgs(**config_args))
```
### Pulumi preview structure
Example pulumi preview will look like:
```
Previewing update (dev):
     Type                                    Name                          Plan       Info
 +   pulumi:pulumi:Stack                     swarm-deployment-gcp-dev      create     1 message
 +   ├─ pkg:swarm:SwarmNetwork               test-network-infrastructure   create     
 +   │  ├─ gcp:compute:Network               test-swarm-network            create     
 +   │  ├─ gcp:compute:Subnetwork            test-instance-subnet          create     
 +   │  ├─ gcp:compute:Firewall              test-swarm-internal-firewall  create     
 +   │  ├─ gcp:compute:Firewall              test-ssh-firewall             create     
 +   │  └─ gcp:compute:Firewall              test-service-firewall         create     
 +   └─ pkg:swarm:SwarmCluster               test-swarm-cluster            create     
 +      ├─ gcp:compute:Instance              test-swarm-node-0             create     
 +      ├─ gcp:compute:InstanceTemplate      test-swarm-node-template      create     
 +      ├─ gcp:compute:InstanceFromTemplate  test-swarm-node-1             create     
 +      └─ gcp:compute:InstanceFromTemplate  test-swarm-node-2             create     
```

## Cleanup
To destroy all resource in the stack run `pulumi down`.
The "deployer" ssh key might still remain in your ssh agent afterward and may need removing.  


# ABOUT US
Mesoform is a specialist software engineering company and are experts in DevOps, SRE and Platform Engineering spaces.

## Contributing
Please read:

* [CONTRIBUTING.md](https://github.com/mesoform/documentation/blob/master/CONTRIBUTING.md)
* [CODE_OF_CONDUCT.md](https://github.com/mesoform/documentation/blob/master/CODE_OF_CONDUCT.md)


## License
This project is licensed under the [MPL 2.0](https://www.mozilla.org/en-US/MPL/2.0/FAQ/)
