## Build OpenFOAM apptainer containers

1. Supply a configuration file (look at [config.yaml](config.yaml) for an example)
2. Run the build playbook and point to the configuration:
```bash
git clone https://github.com/FoamScience/openfoam-apptainer-packaging /tmp/of_tainers
ansible-plabook /tmp/of_tainers/build.yaml --extra-vars "@/path/to/config.yaml"
```

A configuration file for building an (OpenCFD) OpenFOAM container should look like:
```yaml
containers:
  basic:
    opencfd-openfoam: 
      os:
        distro: ubuntu 
        version: 24.04 
      mpi:
        implementation: openmpi 
        version: 4.1.5 
      openfoam:
        fork: com-openfoam 
        version: 2312 
```

You will then find `containers/basic/opencfd-openfoam.sif` (relative to where you run the ansible command).

## Build containers for your OpenFOAM projects

1. Add your project to the configuration file.
2. Write a [definition file](https://apptainer.org/docs/user/main/definition_files.html) for your project.
3. Run the build playbook.

For building a `test` project on top of the `opencfd-openfoam` container:
```yaml
containers:
  basic:
    opencfd-openfoam:
      os:
        distro: ubuntu
        version: 24.04
      mpi:
        implementation: openmpi
        version: 4.1.5
      openfoam:
        fork: com-openfoam
        version: 2312
  projects:
    test:
      base_container: opencfd-openfoam
      definition: projects/test.def
      build_args:
        branch:
          - master
          #- dev
```

The build playbook will create `containers/projects/test-master.sif` for you.

Note that the `build_args` in each project's description is **optional** but can be useful
in building different container versions of the same project. A popular use case is to
compile different branches of a project, or use different compilation modes (eg. optimization/debug).

These `build_args` will translate to apptainer build arguments. For example, `{{ BRANCH }}` (note, all uppercase)
can be used as a placeholder in `projects/test.def` definition file.

The definition files should also follow a set of rules:

- The bootstrapping should be set to `localimage`, and `{{ BASE_CONTAINER }}` should be used as follows:
```bash
Bootstrap: localimage
From: containers/basic/{{ BASE_CONTAINER }}.sif
```
- Even though the build argument for base images will be passed on the command line; it's recommended
  to give default values for them in the definition file anyway
```bash
%arguments
    BASE_CONTAINER=opencfd-openfoam
    OS_VERSION=24.04
    OPENMPI_VERSION=4.1.5
    OPENFOAM_VERSION=2312
    OPENFOAM_GIT_REF=default
```
- In the definition file, important metadata about the container should be logged to `/apps.json`. Refer to
  the [projects/test.def](projects/test.def) example for inspiration.
- If your project requires sourcing an environment file (`.bashrc` or the like), it's good practice to set
  the `%runscript` section so that the file is sourced before the user is dropped into a shell for an
  interactive session. Refer to [basic/com-openfoam.def](basic/com-openfoam.def) for an example.

## Best practices for container usage

```bash
# Note the quoting of the command for openfoam-based containers (since it is fed to Bash as-is)
apptainer run containers/projects/test-master.sif "jq '.' /apps.json"
```
```json
{
  "openmpi": {
    "version": "4.1.5"
  },
  "openfoam": {
    "fork": "com-openfoam",
    "branch": "default",
    "commit": "default",
    "version": "2312"
  },
  "test": {
    "ompi_test_bin": "/opt/OMPIFoam/ompiTest",
    "foam_test_bin": "/opt/OMPIFoam/testOMPIFoam",
    "branch": "master"
  }
}
```

Although it is up to the maintainer to decide what to put in the metadata,
each project container will (usually) log important metadata to its `/apps.json`
which can be queried with `jq`.

The previous snippet suggests that the container provides two executables for testing
the OpenMPI implementation, and that is built on top of `(OpenCFD) OpenFOAM v2312`. Because
this is a version tag, `openfoam.branch` and `openfoam.commit` are set to `default` in the base
container, but if OpenFOAM is to be built from source, it's recommended to set these to
the actual values.

An integral part of this packaging system is the **compatibility with OpenMPI**.
All containers are useable with `mpiexec` and within SLURM batch jobs which is tested in the CI pipeline
for a selected set of containers.

### OpenMPI support

The [config.yaml](config.yaml) file builds a test container to make sure container's MPI runs
smoothly on your host machine:

```bash
# Your host must have OpenMPI as the activate MPI implementation
# Matching the 4.1.5 version is probably optional but recommended; build the containers with your version!
# It's also good practice to share process namespaces with --sharens

# Test a sample MPI application (No OpenFOAM is involved code here)
mpirun -n 2 apptainer run --sharens \
    containers/projects/test-master.sif '/opt/OMPIFoam/ompiTest'
# Should give the same output as:
apptainer run -C \
    containers/projects/test-master.sif 'mpirun -np 2 /opt/OMPIFoam/ompiTest'

# MAKE SURE foam-extend is not sourced (on the host) for the shell instance you run this with
# Also, you can pick any other test container

# Test an OpenFOAM application
mpirun -n 2 apptainer run --cwd /opt/OMPIFoam --sharens \
    containers/projects/test-master.sif '/opt/OMPIFoam/testOMPIFoam -parallel'
# should give the same output as:
apptainer run -C --cwd /opt/OMPIFoam \
    containers/projects/test-master.sif 'mpirun -n 2 /opt/OMPIFoam/testOMPIFoam -parallel'
```

> [!IMPORTANT]
> It's important not to pass `-C` (isolates container environment) to apptainer
> when running MPI applications from the container since the containers use a hybrid approach,
> taking advantage of both the host's OpenMPI installation and the container's one.

### Using project containers

Generally, the containers will source the OpenFOAM environment and any project-specific RC files
before dropping the user at a shell instance. Instead of an interactive shell, it's usually preferred
to run commands through `apptainer run` for reproducibility:
```bash
cd /path/to/openfoam/case/on/host/machine
# apptainer should set CWD to the case folder, so this should 'just work'
apptainer run -C container.sif "./Allclean"
apptainer run -C container.sif "./Allrun.prepare"
mpirun -n 16 apptainer run -C container.sif "containerSolver -parallel"
```

This chain of commands will also work as-is in a SLURM batch script.
