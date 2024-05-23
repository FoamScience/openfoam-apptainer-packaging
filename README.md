# Build apptainer containers for foam-extend-based projects

> [!IMPORTANT]
> Not suitable to run in CI environments because it can log repo tokens, so run this locally only

## Idea

- Build a base `foam-extend` container to run on HPC
- pickup any definitions from `projects` folder to build project-specific containers
  based on the base container

## Instructions

```bash
sudo add-apt-repository -y ppa:apptainer/ppa
sudo apt install -y apptainer
pip install ansible
BITBUCKET_USER=<your_user> BITBUCKET_TOKEN=<your_token> ansible-playbook build.yaml
```

> [!NOTE]
> `ansible` is a nice tool to automate builds and make sure your host system has the required
> dependencies to be able to build the containers.

By default, the playbook builds a single foam-extend container with the following versions:
- Ubuntu: 22.04
- Foam-extend: 5.0
- Foam-extend branch: master
- OpenMPI: 4.1.5
and it will be called `fe-5.0-master-ubuntu-22.04-openmpi-4.1.5.sif`.

To build containers supporting more software versions, add the relevant versions to the definition facts in `build.yaml`.
The playbook also demonstrates how custom project containers can be built by adding `*.def` files to the `projects` folder.

> [!TIP]
> By default, compiling Foam-Extend will use all available CPUs and if you add more software versions to support, the containers
> will be built **in parallel**. You may want to delegate building some containers to other machines.

## OpenMPI support

The `build.yaml` playbook builds a test container which has a test OpenFOAM/MPI application compiled, you 
can test it out like so:

```bash
# Your host must have OpenMPI as the activate MPI implementation
# Matching the 4.1.5 version is probably optional but recommended; build the container with your version!
# but PMI2 / PMIx support must be the same

# Test a simple MPI application
mpirun -n 2 apptainer run -C testOMPI-fe-5.0-master-ubuntu-24.04-ompi-4.1.5.sif /opt/OMPIFoam/ompiTest

# Test an OpenFOAM application
mpirun -np 2 apptainer run -C --cwd /opt/OMPIFoam testOMPI-fe-5.0-master-ubuntu-24.04-ompi-4.1.5.sif '/opt/OMPIFoam/testOMPIFoam -parallel'
# should give same output as:
apptainer run -C --cwd /opt/OMPIFoam testOMPI-fe-5.0-master-ubuntu-24.04-ompi-4.1.5.sif 'mpirun -np 2 /opt/OMPIFoam/testOMPIFoam -parallel'
```

## Notes for container building

- All building steps should carried out by "root" in global folders, eg. `/opt/`, `/usr/lib/`, etc.
- When you run the container, your home folder is mounted, so do not use it for building software.
- It's recommended to always `apptainer run -C` so you isolate your host environment in case you have Foam-Extend sourced there.
