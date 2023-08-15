# Swarm Deployment

* [Summary](#SUMMARY)
* [Description](#DESCRIPTION)
* [How To](#HOW-TO)
    * [Examples](#EXAMPLES)
* [About Us](#ABOUT-US)
    * [Contributing](#Contributing)
    * [License](#License)

# SUMMARY
This repository has the code for deploying some compute instances and initialising a docker swarm.

# DESCRIPTION
This pulumi program creates network infrastructure and compute instances which are all nodes in the same swarm.  

The network components include:
* Subnetwork with specified cidr rang and a secondary range `172.17.0.0/16` for docker communications
* 

# HOW TO
How to get set-up, test and use

## EXAMPLES

Example pulumi preview will look like:
```
Previewing update (dev):
     Type                                    Name                          Plan       Info
 +   pulumi:pulumi:Stack                     swarm-deployment-gcp-dev      create     1 message
 +   ├─ pkg:swarm:SwarmNetwork               capm-network-infrastructure   create     
 +   │  ├─ gcp:compute:Network               capm-swarm-network            create     
 +   │  ├─ gcp:compute:Subnetwork            capm-instance-subnet          create     
 +   │  ├─ gcp:compute:Firewall              capm-swarm-internal-firewall  create     
 +   │  ├─ gcp:compute:Firewall              capm-ssh-firewall             create     
 +   │  └─ gcp:compute:Firewall              capm-service-firewall         create     
 +   └─ pkg:swarm:SwarmCluster               capm-swarm-cluster            create     
 +      ├─ gcp:compute:Instance              capm-swarm-node-0             create     
 +      ├─ gcp:compute:InstanceTemplate      capm-swarm-node-template      create     
 +      ├─ gcp:compute:InstanceFromTemplate  capm-swarm-node-1             create     
 +      └─ gcp:compute:InstanceFromTemplate  capm-swarm-node-2             create     
```

# ABOUT US
Mesoform is a specialist software engineering company and are experts in DevOps, SRE and Platform Engineering spaces.

## Contributing
Please read:

* [CONTRIBUTING.md](https://github.com/mesoform/documentation/blob/master/CONTRIBUTING.md)
* [CODE_OF_CONDUCT.md](https://github.com/mesoform/documentation/blob/master/CODE_OF_CONDUCT.md)


## License
This project is licensed under the [MPL 2.0](https://www.mozilla.org/en-US/MPL/2.0/FAQ/)
