# Build apptainer containers for OpenFOAM-based projects

## Idea

Automated workflows to:

- Build a base `OpenFOAM` container (supporting different forks) to run on HPCs
- Build project-specific containers that inherit from the base container

## Quick Instructions

```bash
sudo add-apt-repository -y ppa:apptainer/ppa
sudo apt install -y apptainer
pip install ansible
ansible-playbook build.yaml --extra-vars "@config.yaml"
```

> [!NOTE]
> `ansible` is a nice tool to automate builds and make sure your host system has the required
> dependencies to be able to build the containers.

The ansible command (by default) will:
- Create the following tree in the current working folder:
```
containers/
├── basic
│   ├── opencfd-openfoam.sif
│   └── ubuntu-24.04-ompi-4.1.5.sif
└── projects
    └── test-master.sif
```
- Build a basic OpenMPI container `containers/basic/ubuntu-24.04-ompi-4.1.5.sif` 
- Build a base (OpenCFD) OpenFOAM container `containers/basic/opencfd-openfoam.sif`
- Build a test project container, to make sure MPI works alright

Check [docs.md](docs.md) for details how the configuration is expected to be structured.

Here is a simplified sequence diagram describing the expected workflow:
```mermaid
sequenceDiagram
  actor User
  participant Ansible Playbook
  participant GHCR
  participant Docker Hub
  participant Local Build
  participant OpenMPI Container
  participant OpenFOAM Container
  participant Project Container

  User->>Ansible Playbook: Start playbook with config.yaml
  Ansible Playbook->>GHCR: Check if OpenMPI Container exists
  GHCR-->>Ansible Playbook: OpenMPI Container not found
  Ansible Playbook->>Docker Hub: Pull Ubuntu image
  Docker Hub-->>Ansible Playbook: Ubuntu image pulled
  Ansible Playbook->>Local Build: Build OpenMPI Container on top of Ubuntu image
  Local Build-->>OpenMPI Container: OpenMPI Container created
  Ansible Playbook->>GHCR: Check if OpenFOAM Container exists
  GHCR-->>Ansible Playbook: OpenFOAM Container not found
  Ansible Playbook->>Local Build: Build OpenFOAM Container on top of OpenMPI Container
  Local Build-->>OpenFOAM Container: OpenFOAM Container created
  Ansible Playbook->>Local Build: Build Project Container on top of OpenFOAM Container with build args
  Local Build-->>Project Container: Project Container created
  Project Container-->>User: Container ready for use
```
