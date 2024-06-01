## Container building guide

### Basic container builds

The containers are built in layers:
1. The OpenMPI library (level 0 containers)
2. The OpenFOAM fork (level 1 containers)
3. The target project library (level 2 containers)

We keep minimal metadata (`%label` section in definition files)
in the container so users can easily see what is installed.

The simplest way to build a container is as follows:
```bash
apptainer build ompi.sif openmpi.def # will use default versions
apptainer build --build-arg OPENMPI_VERSION=4.1.5 ompi.sif openmpi.def # will use the specified version
```

> Of course proper naming of level 0 (and 1) containers is necessary to build later layers.
> But, here, we are only experimenting with the OpenMPI container.

Each container will write its metadata to `/apps.json`. This location is kept as a label:
```bash
apptainer inspect ompi.sif
```

```bash
AppsFile: /apps.json
Description: Ubuntu-based OpenMPI image
...
```

You can query the metadata with [`jq`](https://jqlang.github.io/jq/) for installed
software pieces:
```bash
apptainer run ompi.sif jq '.' /apps.json
```

```json
{
  "openmpi": {
    "version": "4.1.5"
  }
}
```

> [!IMPORTANT]
> You can also get an interactive shell inside the container:
> ```bash
> apptainer run ompi.sif
> ```

The standard way to add a new app to `/apps.json` on later layers of the container is:
```bash
# in %post section of the definition file
# This keeps whatever was in /apps.json but adds the new entry
# called "newapp", with a commit value
# The commit is just an example, anything goes as long as
# /apps.json stays a valid JSON file
jq --arg app newapp \
    '.[$app] |= if . == null then
    {
        commit: "{{ COMMIT_HASH }}"
    }
    else . +
    {
        commit: "{{ COMMIT_HASH }}"
    } end' /apps.json > /tmp/apps.json
mv /tmp/apps.json /apps.json
```

### Notes for container building

- All building steps should be carried out by "root" in global locations, eg. `/opt/`, `/usr/lib/`, etc.
- When you run the container, your home folder is mounted, so do not use it for building software.
- It is assumed that the containers will be used to act on the host's home folder content.

### Ansible for automated building

The provided `build.yaml` is a sophisticated Ansible playbook to make sure required software pieces
are installed locally, and to help automatizing the container building process.

The first two container layers (OpenMPI and OpenFOAM-fork) translate into "Ansible facts",
which can be overridden by including a `software_versions.yaml` file (see the example file used
by CI actions). The default values look like this:
```yaml
openfoam_forks:
  - name: foam-extend
    versions:
      - "5.0"
    branches:
      - master
  - name: com-openfoam
    versions:
      - "2312"
  - name: org-openfoam
    versions:
      - "11"
ubuntu_versions:
  - "24.04"
  - "22.04"
openmpi_versions:
  - "4.1.5"
```

To build containers with specific software versions, adding the versions to these lists is sufficient.

> [!NOTE]
> Notice that `branches` is optional. It is used only in cases where the software piece is compiled
> from source. For example, if the application is installed from a Debian package, the branch will always
> take a default value of 'default'

A build matrix is constructed later from all possible combinations of these versions which is used
to construct the base OpenFOAM containers (inside `containers` folder).
It represents the main "choke point" for gathering build information from user input in previously set facts.
And it also provides a convenient point to filter out which build combinations make sense.

Each OpenFOAM fork has its own definition file, and later,
project definition files are looked up in corresponding folders `projects-<openfoam-fork>`
to build project-specific containers. The build matrix again comes in handy here as projects are expected
to compile with specific forks of OpenFOAM but generally assumed to compile across versions of the same
fork:
```bash
openmpi.def # lvl 0 container
foam-extend.def # lvl 1
com-openfoam.def # lvl 1
org-openfoam.def # lvl 1
projects-foam-ext/test.def # lvl 2
projects-com-openfoam/test.def # lvl 2
```

The build matrix is crossed with the projects `*.def` files list to determine which projects
should be built for which OpenFOAM forks.

> [!TIP]
> Due to the differences in Debian packages for different OpenFOAM forks, OpenFOAM is installed to:
> - `/usr/lib/openfoam/openfoam<version>` for `com-openfoam`
> - `/opt/openfoam<version>` for `org-openfoam`
> - `/opt/foam/foam-extend-<version>` for `foam-extend` (This one was a personal choice)
>
> You may want to use [spack](https://spack.readthedocs.io/en/latest/) to install all OpenFOAM forks
> from sources if you wish to have more control. Usually, this is time (and disk-space) consuming
> so the binary packages are preferred.

## Container usage guide

Typically, only level 2 containers are destined for direct usage.
These are the final application containers:
```bash
# Note the quoting of the command for openfoam-based containers (since it is fed to Bash as is)
# Containers created from the `projects-com-openfoam/test.def` definition file
apptainer run containers/test-com-openfoam-default-ubuntu-24.04-ompi-4.1.5.sif "jq '.' /apps.json"
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
    containers/test-foam-extend-5.0-master-ubuntu-24.04-ompi-4.1.5.sif \
    '/opt/OMPIFoam/ompiTest'
# Should give the same output as:
apptainer run -C \
    containers/test-foam-extend-5.0-master-ubuntu-24.04-ompi-4.1.5.sif \
    'mpirun -np 2 /opt/OMPIFoam/ompiTest'

# MAKE SURE foam-extend is not sourced (on the host) for the shell instance you run this with
# Also, you can pick any other test container

# Test an OpenFOAM application
mpirun -n 2 apptainer run --cwd /opt/OMPIFoam --sharens \
    containers/test-foam-extend-5.0-master-ubuntu-24.04-ompi-4.1.5.sif \
    '/opt/OMPIFoam/testOMPIFoam -parallel'
# should give the same output as:
apptainer run -C --cwd /opt/OMPIFoam \
    containers/test-foam-extend-5.0-master-ubuntu-24.04-ompi-4.1.5.sif \
    'mpirun -n 2 /opt/OMPIFoam/testOMPIFoam -parallel'
```

> [!IMPORTANT]
> It's important not to pass `-C` (isolates container environment) to apptainer
> when running MPI applications from the container since the containers use a hybrid approach,
> taking advantage of both the host's OpenMPI installation and the container's one.

