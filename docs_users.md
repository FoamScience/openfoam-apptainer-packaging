## Container usage guide

Typically, only project containers are destined for direct usage.
These are the final application containers:
```bash
# Note the quoting of the command for openfoam-based containers (since it is fed to Bash as is)
# Containers created from the `projects-com-openfoam/test.def` definition file
apptainer run containers/test/test-com-openfoam-2312-default-ubuntu-24.04-ompi-4.1.5.sif "jq '.' /apps.json"
```
```json
{
  "openmpi": {
    "version": "4.1.5"
  },
  "openfoam": {
    "fork": "foam-extend",
    "branch": "master",
    "commit": "287705b4a5896510f1230eea5e528dd0f304f1df",
    "version": "5.0"
  },
  "test": {
    "ompi_test_bin": "/opt/OMPIFoam/ompiTest",
    "foam_test_bin": "/opt/OMPIFoam/testOMPIFoam"
  }
}
```

Although it is up to the maintainer to decide what to put in the metadata,
each application container will (usually) log important metadata to its `/apps.json`
which can be queried with `jq`.

The previous snippet suggests that the container provides two binary executables for testing
the OpenMPI implementation, and that is built on top of `foam-extend-5.0`'s master branch which
was at commit `287705b` at the time of building the container.

An integral part of this packaging system is the **compatibility with OpenMPI**.
All containers are useable with `mpiexec` and within SLURM batch jobs which is tested in the CI pipeline
for a selected set of containers.

## OpenMPI support

The `build.yaml` playbook builds test containers for each supported OpenFOAM fork, which test
OpenFOAM/MPI applications:

```bash
# Your host must have OpenMPI as the activate MPI implementation
# Matching the 4.1.5 version is probably optional but recommended; build the containers with your version!
# It's also good practice to share process namespaces with --sharens

# Test a sample MPI application (No OpenFOAM is involved code here)
mpirun -n 2 apptainer run --sharens \
    containers/test/test-com-openfoam-2312-default-ubuntu-24.04-ompi-4.1.5.sif \
    '/opt/OMPIFoam/ompiTest'
# Should give the same output as:
apptainer run -C \
    containers/test/test-com-openfoam-2312-default-ubuntu-24.04-ompi-4.1.5.sif \
    'mpirun -np 2 /opt/OMPIFoam/ompiTest'

# MAKE SURE foam-extend is not sourced (on the host) for the shell instance you run this with
# Also, you can pick any other test container

# Test an OpenFOAM application
mpirun -n 2 apptainer run --cwd /opt/OMPIFoam --sharens \
    containers/test/test-com-openfoam-2312-default-ubuntu-24.04-ompi-4.1.5.sif \
    '/opt/OMPIFoam/testOMPIFoam -parallel'
# should give the same output as:
apptainer run -C --cwd /opt/OMPIFoam \
    containers/test/test-com-openfoam-2312-default-ubuntu-24.04-ompi-4.1.5.sif \
    'mpirun -n 2 /opt/OMPIFoam/testOMPIFoam -parallel'
```

> [!IMPORTANT]
> It's important not to pass `-C` (isolates container environment) to apptainer
> when running MPI applications from the container since the containers use a hybrid approach,
> taking advantage of both the host's OpenMPI installation and the container's one.

## Using project containers

Generally, the containers will source the OpenFOAM environment and any project-specific RC files
before dropping the user at a shell instance. Instead of an interactive shell, it's usually better
to run commands through `apptainer run`:
```bash
cd /path/to/openfoam/case/on/host/machine
apptainer run -C container.sif "./Allclean"
apptainer run -C container.sif "./Allrun.prepare"
mpirun -n 16 apptainer run -C container.sif "containerSolver -parallel"
```

This chain of commands will also work as is in a SLURM batch script.
