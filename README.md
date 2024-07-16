# Build apptainer containers for your projects

<p align="center">
<img alt="GitHub Actions Workflow Status" src="https://img.shields.io/github/actions/workflow/status/FoamScience/openfoam-apptainer-packaging/ci.yaml?style=for-the-badge&logo=linuxcontainers&label=Test%20container">
<img alt="OpenCFD OpenFOAM" src="https://img.shields.io/badge/OpenCFD_OpenFOAM-blue?style=for-the-badge">
<img alt="Foundation OpenFOAM" src="https://img.shields.io/badge/Foundation_Version-darkgreen?style=for-the-badge">
<img alt="Foam Extend" src="https://img.shields.io/badge/Foam_Extend-teal?style=for-the-badge">
</p>

This is a project to automate building HPC-ready containers (originally for OpenFOAM-based projects)
using `apptainer`.

> [!NOTE]
> Brought to you by SDL Energy Conversion from
> <a href="https://www.nhr4ces.de/simulation-and-data-labs/sdl-energy-conversion/">
> <img src="https://www.itc.rwth-aachen.de/global/show_picture.asp?id=aaaaaaaabvbpmgd&w=223&q=77" alt="NHR4CES" height="50px" style="vertical-align:middle"/>
> </a>
> in collaboration with
> <a href="https://ianus-simulation.de/en/">
> <img src="https://ianus-simulation.de/wp-content/uploads/2023/04/IANUS_Logo_color_color_bold_RGB.png" alt="IANUS SIMULATION" height="30px" style="vertical-align:middle"/>
> </a>.

## Idea

Automated workflows to:

- Build a base framework (eg: `OpenFOAM`) container (supporting various forks and versions) to run on HPCs
- Build project-specific containers that inherit from a target base container
- OpenMPI is a first-class citizen: `mpirun -n 16 apptainer run container.sif "solver -parallel"`
  should 'just work'.

## Highlighted features

1. Automated, configuration-only workflows to produce containers that behave similarly across frameworks.
1. A JSON Database of container metadata, with full control at the hands of the container maintainer.
1. Maintaining definition files for your projects can be done in your own repos.
1. Loading your own repositories of base framework container definitions works seamlessly.

## Quick Instructions

```bash
sudo add-apt-repository -y ppa:apptainer/ppa
sudo apt install -y apptainer
pip install ansible
ansible-playbook build.yaml --extra-vars "original_dir=$PWD" --extra-vars "@config.yaml"
```

> [!TIP]
> `ansible` is a nice tool to automate builds and make sure your host system has the required
> dependencies to be able to build the containers. The configuration file and base definitions
> provided serve as examples to build OpenFOAM containers.

The ansible command (by default) will:
- Create the following tree in the current working folder:
```
containers/
├── basic
│   ├── opencfd-openfoam.sif
│   └── ubuntu-24.04-openmpi-4.1.5.sif
└── projects
    └── test-master.sif
```
- Build a basic OpenMPI container `containers/basic/ubuntu-24.04-openmpi-4.1.5.sif`, or
  pull it from [ghcr.io](https://ghcr.io) if possible
- Build a base (OpenCFD) OpenFOAM container `containers/basic/opencfd-openfoam.sif`, or
  pull it from [ghcr.io](https://ghcr.io) if possible
- Build a test project container, to make sure MPI works alright in OpenFOAM containers

Check the [docs.md](docs.md) for details on how the configuration file
is expected to be structured.

Here is a simplified sequence diagram describing the expected workflow:
```mermaid
sequenceDiagram
  actor User
  participant Ansible Playbook
  participant GHCR
  participant Docker Hub
  participant Local Build
  participant MPI Container
  participant Framework Container
  participant Project Container

  User->>Ansible Playbook: Start playbook with config.yaml
  Ansible Playbook->>GHCR: Check if MPI Container exists
  GHCR-->>Ansible Playbook: MPI Container not found
  Ansible Playbook->>Docker Hub: Pull Ubuntu image
  Docker Hub-->>Ansible Playbook: Ubuntu image pulled
  Ansible Playbook->>Local Build: Build MPI Container on top of Ubuntu image
  Local Build-->>MPI Container: MPI Container created
  Ansible Playbook->>GHCR: Check if Framework Container exists
  GHCR-->>Ansible Playbook: Framework Container not found
  Ansible Playbook->>Local Build: Build Framework Container on top of MPI Container
  Local Build-->>Framework Container: Framework Container created
  Ansible Playbook->>Local Build: Build Project Container on top of Framework Container with build args
  Local Build-->>Project Container: Project Container created
  Project Container-->>User: Container ready for use
```
