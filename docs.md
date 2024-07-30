> [!IMPORTANT]
> We take OpenFOAM as an example here, but containers for any other HPC software
> package can be built in the same way.

## Build apptainer containers for OpenFOAM 

You only need to:

1. Supply a configuration file (look at [config.yaml](config.yaml) for an example)
2. Run the build playbook and point to the configuration:
```bash
git clone https://github.com/FoamScience/openfoam-apptainer-packaging /tmp/of_tainers
ansible-playbook /tmp/of_tainers/build.yaml \
    --extra-vars "original_dir=$PWD" \
    --extra-vars "@/path/to/config.yaml"
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
      framework:
        definition: com-openfoam 
        version: 2312 
```

You will then find the resulting container at `containers/basic/opencfd-openfoam.sif`
(relative to where you run the ansible command). Note that, by default, the build playbook
will try to pull some base containers from a registry, and build them only if the pull is
unsuccessful. Pull-related behaviour can be configured in a `pull` section
(again, refer to [config.yaml](config.yaml) for an example).

## Build containers for your OpenFOAM-based projects

1. Add your project to the configuration file.
2. Write a [definition file](https://apptainer.org/docs/user/main/definition_files.html) for your project.
3. Run the build playbook.

To build a `test` project on top of the `opencfd-openfoam` container, supply the
following configuration file:
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
      framework:
        definition: com-openfoam
        version: 2312
  projects:
    test:
      base_container: opencfd-openfoam
      definition: projects/test.def # This is always relative to CWD (original_dir)
      build_args:
        branch:
          - master
          #- dev
```

The build playbook will then create `containers/projects/test-master.sif` for you.

The `build_args` in each project's description is **optional** but can be useful
when building different container versions of the same project. A popular use case is to
compile different branches of a project, or use different compilation modes
(eg. optimized/debug containers).

The `build_args` will translate to `apptainer` build arguments. For example,
`{{ BRANCH }}` (note, all uppercase) can be used as a placeholder in `projects/test.def`
definition file. It will be replaced with the possible values of `build_args.branch`.

The definition files should also follow a set of rules:

- The bootstrapping should be set to `localimage`,
  and the appropriate build arguments should be used as follows:
```bash
Bootstrap: localimage
From: {{ CONTAINERS_DIR }}/basic/{{ BASE_CONTAINER }}.sif
```
- Even though the build argument for base images will be passed on the command line;
  it's recommended to give default values for them in the definition file anyway
```bash
%arguments
    BASE_CONTAINER=opencfd-openfoam
    OS_DISTRO=ubuntu
    OS_VERSION=24.04
    MPI_IMPLEMENTATION=openmpi
    MPI_VERSION=4.1.5
    FRAMEWORK_VERSION=2312
    FRAMEWORK_GIT_REF=default
```
- In the definition file, important metadata about the container should be logged to `/apps.json`. Refer to
  the [projects/test.def](projects/test.def) example for inspiration.
- If your project requires sourcing an environment file (`.bashrc` or the like), it's good practice to set
  the `%runscript` section so that the file is sourced before the user is dropped into a shell for an
  interactive session. Refer to [basic/com-openfoam.def](basic/com-openfoam.def) for an example.

## Best practices for container usage

> [!TIP] 
> The default containers are designed to run in an as-is state, only writing to your home folder.
> If you need to constantly change stuff in `/opt` for example inside the container, you have
> to create an overlay image and load it with the container when running it:
> ```bash
> apptainer overlay create --size 1024 overlay.img
> apptainer run --overlay overlay.img <your-container>.sif
> ```
> This is useful for example if you want to continuously develop on the container. Learn more
> about [Persistent Overlays](https://apptainer.org/docs/user/latest/persistent_overlays.html)

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

# Test a sample MPI application (No OpenFOAM code is involved here)
mpirun -n 2 apptainer run --sharens containers/projects/test-master.sif '/opt/OMPIFoam/ompiTest'
# Should give the same output as:
apptainer run -C containers/projects/test-master.sif 'mpirun -np 2 /opt/OMPIFoam/ompiTest'

# MAKE SURE OpenFOAM is not sourced (on the host) for the shell instance you run this with
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
to run commands through `apptainer run` for reproducibility reasons:
```bash
cd /path/to/openfoam/case/on/host/machine
# apptainer should set CWD to the case folder, so this should 'just work'
apptainer run -C container.sif "./Allclean"
apptainer run -C container.sif "./Allrun.prepare"
mpirun -n 16 apptainer run --sharens container.sif "containerSolver -parallel"
```

This chain of commands will also work as-is in a SLURM batch script.

## Container debugging

The apptainer images are meant to be used without any additional software packages to be
installed or compiled into the containers, so create your definition files accordingly;
but just in case you need to take a look at what's exactly inside the container,
Docker can be useful, especially for comparing the container to a base image:
```bash
# Convert the container SIF to a sandbox directory
apptainer build --sandbox ubuntu-24.04-ompi-4.1.5 ubuntu-24.04-ompi-4.1.5.sif
# Compare the sandbox folder to the base docker Ubuntu image
# This will show a list of added/removed/upgraded packages
docker scout compare fs://ubuntu-24.04-ompi-4.1.5 --to ubuntu:24.04

# Do we do better than some random Ubuntu-based MPI images?
docker scout compare fs://ubuntu-24.04-ompi-4.1.5 --to csirocass/mpi:ubuntu22.04-openmpi4

# Scan the sandbox directory for vulnerabilities. As long as no "critical" CVEs are found,
# we can live with the rest
docker scout quickview fs://ubuntu-24.04-ompi-4.1.5
# More details on CVEs if you care about them. Generally, upgrading software gets rid
# of most of the vulnerabilities
docker scout cves fs://ubuntu-24.04-ompi-4.1.5
```

## Load your own base containers

The `config.yaml` file can take a `containers.extra_basics` entry, which can be either a
git URI or a local path to a folder containing a `basic` subfolder which hosts your custom
definition files for basic containers. These definitions will then be usable as
`containers.basic.<container-name>.framework.definition`
and even `containers.basic.<container-name>.mpi.implementation`.

The  [spack-apptainer-containers](https://github.com/FoamScience/spack-apptainer-containers)
repository demonstrates how custom base images can be used to build spack-powered containers


In `/tmp/spack_containers/basic/spack_openmpi.def` you can have:
```
Bootstrap: docker
From: {{ OS_DISTRO }}:{{ OS_VERSION }}
# This will expand to
# From: spack/ubuntu-bionic:latest

%post
    . /opt/spack/share/spack/setup-env.sh
    # MPI_IMPLEMENTATION will be "spack_openmpi" as specified in the config
    mpi_impl=$(expr "{{ MPI_IMPLEMENTATION }}" : 'spack_\(.*\)')
    spack install ${mpi_impl}@{{ MPI_VERSION }} jq
```
> `/tmp/spack_containers/basic/spack_openfoam.def` is also very similar
> but must base itself off of the generated MPI container. Look at
> [spack-apptainer-containers](https://github.com/FoamScience/spack-apptainer-containers)
> for an example implementation

And the basic container in `config.yaml` can look like this:
```yaml
containers:
  extra_basics: https://github.com/FoamScience/spack-apptainer-containers
  basic:
    spack_openfoam: # you get containers/basic/spack_openfoam.sif
      os:
        distro: spack_ubuntu-bionic # the underscore will be converted to / inside the definition files
                # so this bases the container off the spack/ubuntu-bionic:latest docker image
                # To build on top of setup, change this to spack_centos7
                # BUT this may not always work, an experimental feature at best
        version: latest
      mpi:
        implementation: spack_openmpi # looks for spack_openmpi.def in basic folder
        version: 4.1.5
      framework:
        definition: spack_openfoam # looks for spack_openfoam.def in basic folder
        version: 2312
```

It's important to understand that the ansible playbook will always generate containers with MPI support
as a first layer, then generate the basic framework container on top of that.

> [!IMPORTANT]
> Although definition files leveraging `spack` will be generally shorter and easier to maintain, the resulting
> containers will be much larger than using distribution package managers. Also, at the time of writing,
> `spack` doesn't allow for easy switching of the underlying distribution as random installation errors
> arise for the same definition file if you base it on ubuntu and centos 7 images.
