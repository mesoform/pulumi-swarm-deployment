from setuptools import find_packages, setup

setup(
    name='swarm-deployment',
    version='0.1',
    description='Deploy docker swarm to cloud provider',
    author='Alex Bailey',
    author_email='alex.bailey@mesoform.com',
    packages=find_packages(include=['swarm_deployment_gcp', 'swarm_deployment_gcp.*']),
    install_requires=[
        'pulumi',
        'pulumi-gcp',
        'requests',
        'cryptography'
    ],
    python_requires=">=3.10"
)

