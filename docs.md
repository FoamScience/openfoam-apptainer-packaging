## Container building guide

### Basic container builds

The containers are built in layers:
1. The OpenMPI library
2. The OpenFOAM fork
3. The target project library

We keep minimal metadata (`%label` section in definition files) in the container so users can easily see what is installed.

The simplest way to build a container:
```bash
apptainer build ompi.sif openmpi.def # will use default versions
apptainer build --build-arg OPENMPI_VERSION=4.1.5 ompi.sif openmpi.def # will use the specified version
```

Each container will write its metadata to `/apps.json`. This location is kept as a label:
```bash
apptainer inspect ompi.sif
```

```bash
AppsFile: /apps.json
Description: Ubuntu-based OpenMPI image
...
```

You can query the metadata with `jq` for software versions:
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

The standard way to add a new app on later layers of the container is:
```bash
# in %post section of the definition file
# This keeps whatever was in /apps.json but adds the new entry
# called "newapp", with a commit value
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
- It is assumed that the containers will be used to act on home folder content on the host.

### Ansible for automated building

The provided `build.yaml` is a sophisticated Ansible playbook that makes sure required software is installed locally,
and helps automatizing the container building process.

The first two layers translate into "Ansible facts":
```yaml
- name: Set facts for OpenFOAM forks, Ubuntu, and Open MPI versions
  hosts: "{{ groups['build_hosts'] | default('localhost') }}"
  gather_facts: no
  tasks:
    - name: Set OpenFOAM forks, versions, Ubuntu, and OpenMPI versions
      set_fact:
        openfoam_forks:
          - name: foam-extend
            versions:
              - "5.0"
            branches:
              - master
          - name: com-openfoam
            versions:
              - "2312"
              - "2212"
        ubuntu_versions:
          - "24.04"
        openmpi_versions:
          - "4.1.5"
```
To build containers with specific software versions, adding the versions to these lists is sufficient.

> [!NOTE]
> Notice that `branches` is optional. It is used only in cases where the software piece is compiled
> from source. For example, if the application is installed from a Debian package, the branch will always
> take a default value of 'default'

A build matrix is constructed later from all possible combinations of these versions:
```yaml
    - name: Software combinations
      set_fact:
        structured_list: "{{ (structured_list | default([])) + (item.versions | product(item.branches | default(['default']), [item.name])) }}"
      loop: "{{ openfoam_forks | list }}"
    - name: Build matrix
      set_fact:
        build_matrix: "{{ build_matrix | default([]) + [dict({'version': item.0.0, 'branch': item.0.1, 'fork': item.0.2, 'ubuntu': item.1, 'openmpi': item.2 })] }}"
      loop: "{{ structured_list | product(ubuntu_versions, openmpi_versions) }}"
```
 
This build matrix is used to construct the base OpenFOAM containers (inside `containers` folder).
It represents the main "choke point" for gathering build info from user input in previously set facts.
And it also provides a convenient point to filter out which build combinations make sense.

Each OpenFOAM fork has its own definition file, and later,
project definition files are looked up in corresponding folders `projects-<openfoam-fork>`
to build project-specific containers. The build matrix comes in handy here as projects are expected
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

The build matrix is crossed with the projects files list to determine which projects
should be built for which OpenFOAM forks.

> [!TIP]
> Due to the differences in Debian packages for different OpenFOAM forks, OpenFOAM is installed to:
> - `/usr/lib/openfoam/openfoam<version>` for `com-openfoam`
> - `/opt/openfoam<version>` for `org-openfoam`
> - `/opt/foam/foam-extend-<version>` for `foam-extend`
>
> You may want to use [spack](https://spack.readthedocs.io/en/latest/) to install all OpenFOAM forks
> from sources if you wish to have more control. Usually, this is time (and disk-space) consuming
> so the binary packages are preferred.

## Container usage guide

Typically, only level 2 containers are destined for direct usage. These are the final application containers:
```bash
# Note the quoting of the command for openfoam-based containers (since it is fed to Bash as is)
# Container created from the `projects-com-openfoam/test.def` definition file
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

Although it is up to the container maintainer to decide what to put in the metadata,
each application container will (usually) log important metadata to its `/apps.json`
which can be queried with `jq`.

The previous snippet suggests that the container provides two binary executables for testing
the OpenMPI implementation.

An integral part of this packaging system is compatibility with OpenMPI. All containers are useable
with `mpiexec` and within SLURM batch jobs.

## OpenMPI support

The `build.yaml` playbook builds test containers for each supported OpenFOAM fork, which test
OpenFOAM/MPI applications:

```bash
# Your host must have OpenMPI as the activate MPI implementation
# Matching the 4.1.5 version is probably optional but recommended; build the containers with your version!
# It's also good practice to share process namespaces with --sharens

# Test a sample MPI application (NO OpenFOAM code here)
mpirun -n 2 apptainer run --sharens \
    containers/test-foam-extend-5.0-master-ubuntu-24.04-ompi-4.1.5.sif \
    '/opt/OMPIFoam/ompiTest'
# Should give the same output as:
apptainer run -C \
    containers/test-foam-extend-5.0-master-ubuntu-24.04-ompi-4.1.5.sif \
    'mpirun -np 2 /opt/OMPIFoam/ompiTest'

# MAKE SURE foam-extend is not sourced (on the host) for the shell instance you run this with

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
> It's important not to pass `-C` (isolates container environment) when running
> MPI applications from the container since the containers use a hybrid approach,
> taking advantage of both the host's OpenMPI installation and the container's one.

