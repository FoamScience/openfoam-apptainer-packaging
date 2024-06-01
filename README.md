# Build apptainer containers for foam-extend-based projects

> [!IMPORTANT]
> Not suitable to run in CI environments because it can log repo tokens, so run this locally only

## Idea

- Build a base `OpenFOAM` container (supporting different forks) to run on HPCs
- pickup any definitions from `projects-<openfoam-fork>` folder to build project-specific containers
  based on the base container

## Quick Instructions

```bash
sudo add-apt-repository -y ppa:apptainer/ppa
sudo apt install -y apptainer
pip install ansible
ansible-playbook build.yaml
```

> [!NOTE]
> `ansible` is a nice tool to automate builds and make sure your host system has the required
> dependencies to be able to build the containers.

The ansible command will:
- Build two intermediary OpenMPI containers (for ubuntu `22.04` and `24.04`).
- Build the base OpenFOAM containers for `foam-extend`, OpenCFD OpenFOAM (`com-openfoam`),
  and the foundation version (`org-openfoam`) for each OpenMPI container.
- Build containers from the test definition files in `projects-<openfoam-fork>`
- Note that, currently, there is no debian packages for OpenFOAM v11 on Ubuntu 24 so
  the build matrix avoids this case.

Take a look at [docs.md](docs.md) for more details on building and using the containers.
