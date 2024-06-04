## Container building guide

### Basic container builds

The containers are built in layers:
1. The OpenMPI library (from definitions in `basic`, to `containers` folder)
2. The OpenFOAM fork (from definitions in `basic`, to `containers` folder)
3. The target project library (from definitions in `projects-<openfoam-fork>` folders)

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
- It is assumed that the project containers will be used to act on the host's home folder content.

### Ansible for automated building

The provided `build.yaml` is a sophisticated Ansible playbook to make sure required software pieces
are installed locally, and to help automatizing the container building process.

Most of the time, there will be no need to make any changes to `build.yaml` or any `partial`
build tasks. All you have to do is to provide two files:
- `project_versions.yaml` (mandatory) to specify the projects you want to build
- `software_versions.yaml` (optional) to specify the dependency software versions
  (Ubuntu, OpenMPI and OpenFOAM) you want to build your projects against
 
The default values for the `software_versions.yaml` file (see the example file used
by CI actions) look like this:
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

A build matrix is constructed later from all possible combinations of these versions and then is used
to construct the base OpenFOAM containers (inside `containers` folder).
It represents the main "choke point" for gathering build information from user input in previously set facts.
And it also provides a convenient point to filter out which build combinations make sense.

Each OpenFOAM fork has its own definition file (inside the `basic` folder), and later,
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

The build matrix is crossed with the projects entries from `project_versions.yaml` to determine which projects
should be built for which OpenFOAM forks. This allows passing custom build arguments to the `apptainer build`
command, which enables the ability to compile different versions for the same project. Examples of use
cases for such build arguments are:
- Build different branches of the same project for testing.
- Compile optimized and debug versions of the project's libraries.

An example `project_versions.yaml` file looks like this:
```yaml
# This will build containers for the test project with OpenCFD OpenFOAM (no build args)
# needs com-openfoam-projects/test.def to be present
com-openfoam-projects:
    - name: test
# Same for foam-extend
foam-extend-projects:
    - name: test
# This will build containers for the test project with Foundation OpenFOAM
# needs org-openfoam-projects/test.def to be present
# and you can use '{{ GIT_BRANCH }}' to refer to the git branch in the definition file
org-openfoam-projects:
    - name: test
        GIT_BRANCH:
        - master
        - develop
```

You will find the project containers in `containers/<project_name>`.

> [!TIP]
> Due to the differences in Debian packages for different OpenFOAM forks, OpenFOAM is installed to:
> - `/usr/lib/openfoam/openfoam<version>` for `com-openfoam`
> - `/opt/openfoam<version>` for `org-openfoam`
> - `/opt/foam/foam-extend-<version>` for `foam-extend` (This one was a personal choice)
>
> You may want to use [spack](https://spack.readthedocs.io/en/latest/) to install all OpenFOAM forks
> from sources if you wish to have more control. Usually, this is time (and disk-space) consuming
> so the binary packages are preferred.

## Building project containers

To build project containers; two steps are needed:
- Add a definition file named `<project_name>.def` to `projects-<openfoam-fork>`
- Specify build arguments if any in `projects_versions.yaml` (refer to previous section)

The build arguments are optional, but an entry in the corresponding OpenFOAM fork section
in `projects_versions.yaml` is required to build the container (at least the `name` needs
to be provided).

Typically, you'll need to start from a local container that the workflow will build:
```docker
Bootstrap: localimage
From: containers/com-openfoam-{{ OF_VERSION }}-{{ OF_BRANCH }}-ubuntu-{{ UBUNTU_VERSION }}-ompi-{{ OMPI_VERSION }}.sif
```

Apptainer definition files support a `%runscript` section which defines a script to run when `apptainer run` is
invoked. This can be useful in sourcing bash scripts before dropping the user at an interactive shell.
Use `com-openfoam.def` as an example for this.

The `%post` section should be used to compile your project, preferably to global locations, and to register
important metadata to `/apps.json`.

Also, the `%labels` will override base containers' labels if provided, so take advantage of them
to set expressive descriptions and add or change maintainers.

For more information on definition file syntax,
see [Apptainer docs](https://apptainer.org/docs/user/main/definition_files.html).
