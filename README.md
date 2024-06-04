# Build apptainer containers for OpenFOAM-based projects

## Idea

- Build a base `OpenFOAM` container (supporting different forks) to run on HPCs
- pickup any definitions from `projects-<openfoam-fork>` folders to build
  project-specific containers

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

The ansible command (by default) will:
- Build two intermediary OpenMPI containers (for ubuntu `22.04` and `24.04`).
- Build the base OpenFOAM containers for `foam-extend`, OpenCFD OpenFOAM (`com-openfoam`),
  and the foundation version (`org-openfoam`) for each OpenMPI container.
- Build containers from the test definition files in `projects-<openfoam-fork>`
- Note that, currently, there is no debian packages for OpenFOAM v11 on Ubuntu 24 so
  the build matrix avoids this case.

If you want to specify different versions, copy the example `software_versions.yaml` file
and edit its contents to your liking:
```bash
# The example file is used for CI by default by testing out only
# one openfoam fork, on ubuntu 24.04, with one OpenMPI version
cp software_versions_example.yaml software-versions.yaml
```
```yaml
openfoam_forks:
  - name: com-openfoam
    versions:
      - "2312"
ubuntu_versions:
  - "24.04"
openmpi_versions:
  - "4.1.5"
```

Take a look at [docs_dev.md](docs_dev.md) for more details on building, and at
[docs_user.md](docs_user.md) for details on how to use them.
