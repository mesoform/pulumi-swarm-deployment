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
### Compute Instances
The program creates and manages compute instances on GCP. The first instance is initialized as the Docker Swarm manager node. 
Subsequent instances join the Swarm using a token saved in Google Secret Manager. Each instance:

- Is associated with a specific machine type as defined in the configuration.
- Has Docker installed and is automatically added to the Docker group.
- Has SSH keys generated and added, allowing SSH access to the instance.

### Network Components
The deployment provisions several networking components:

- The defined swarm network.
- A subnet with a specified CIDR range and a secondary range `172.17.0.0/16` for Docker communications.
- Firewall rules:
  - **Internal Swarm Communication:** Allows nodes in the Swarm to communicate with each other
  - **SSH Access:** Permits SSH access to the instances
  - **Service Access:** If any services are exposed on the nodes, this rule will ensure they're accessible.

### SSH Keys
For automated deployments, an SSH key is generated on the deploying device, and is added to the compute instance.
This allows the deployer to create a docker context to connect and deploy a stack to the swarm cluster.


## How to use module

### Import module

1. Create a pulumi program
2. Include this module in requirements.txt (e.g. `swarm-deployment @ git+https://github.com/mesoform/pulumi-swarm-deployment.git`)
3. Use Component resources in code (see example)

### Cloning
1. Clone this repository.
2. Navigate to the directory containing the Pulumi program.
3. Modify the configuration for the stack
4. Run `pulumi up`. Review the proposed changes and confirm the deployment.


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

# ABOUT US
Mesoform is a specialist software engineering company and are experts in DevOps, SRE and Platform Engineering spaces.

## Contributing
Please read:

* [CONTRIBUTING.md](https://github.com/mesoform/documentation/blob/master/CONTRIBUTING.md)
* [CODE_OF_CONDUCT.md](https://github.com/mesoform/documentation/blob/master/CODE_OF_CONDUCT.md)


## License
This project is licensed under the [MPL 2.0](https://www.mozilla.org/en-US/MPL/2.0/FAQ/)
