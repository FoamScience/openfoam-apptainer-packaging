> [!IMPORTANT]
> We take OpenFOAM as an example here, but containers for any other HPC software
> package can be built in the same way.

<!-- mtoc-start:0f841ef -->

* [Build Apptainer containers for OpenFOAM](#build-apptainer-containers-for-openfoam)
  * [Layered base containers](#layered-base-containers)
* [Build containers for your OpenFOAM-based projects](#build-containers-for-your-openfoam-based-projects)
* [Best practices for container usage](#best-practices-for-container-usage)
  * [OpenMPI support](#openmpi-support)
  * [Using project containers](#using-project-containers)
* [Container debugging](#container-debugging)
* [Load your own base containers](#load-your-own-base-containers)
* [Container Testing](#container-testing)
* [MPI Testing](#mpi-testing)
* [Security Scanning](#security-scanning)
* [Size Analysis](#size-analysis)
* [Report Generation](#report-generation)
  * [Report Structure](#report-structure)
* [Configuration Reference](#configuration-reference)
  * [Basic Containers](#basic-containers)
  * [Project Containers](#project-containers)
  * [Extra Basics](#extra-basics)
  * [Pull Configuration](#pull-configuration)
  * [Build Options](#build-options)
  * [Security Policy](#security-policy)
  * [Testing Configuration](#testing-configuration)
  * [Complete Configuration Example](#complete-configuration-example)

<!-- mtoc-end:0f841ef -->

## Build Apptainer containers for OpenFOAM

You only need to:

1. Install hpcTainers: `uv tool install .` (or use `uvx hpctainers` to run without installing)
2. Supply a configuration file (look at [config.yaml](config.yaml) for an example)
3. Build the containers:
```bash
# Using installed version
hpctainers --config config.yaml

# Or without installation
uvx hpctainers --config config.yaml

# With default config.yaml in current directory
hpctainers
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
(relative to the current working directory). Note that, by default, hpcTainers
will try to pull some base containers from a registry, and build them only if the pull is
unsuccessful. Pull-related behaviour can be configured in a `pull` section
(again, refer to [config.yaml](config.yaml) for an example).

### Layered base containers

The `containers.basic.framework` keyword can be a mapping as shown above, in which case,
a single base framework is expected to be on the container, and can also be a list of frameworks:
```yaml
containers:
  basic:
    openfoam-hpctoolkit: 
      os:
        distro: ubuntu 
        version: 24.04 
      mpi:
        implementation: openmpi 
        version: 4.1.5 
      framework:
        - definition: com-openfoam 
          version: 2312 
        - definition: hpctoolkit
          version: 2024.01.99-next 
```

If a list of frameworks is provided, all will be installed on the container, in order,
by creating intermediary images off of the previous ones, starting from the MPI container.

As for the user environment setup, the most basic image sets up the following automatically:
- All `source_script` (pointing to BASH scripts) entries for `apps.json` entries are sourced.
- All virtual environments from `python_env` entries in `/apps.json` are loaded, in order.
- If an `/apps.json` entry has a `uv_env`, the pointed-to file is sourced. Further
  configuration of [uv](https://github.com/astral-sh/uv) is left to the user, but the following
  is recommended in container context:
  ```bash
  echo "export UV_ENV_FILE=$UV_ENV_FILE" > $UV_ENV_FILE
  echo "export UV_NO_SYNC=1" >> $UV_ENV_FILE
  echo "export UV_COMPILE_BYTECODE=1" >> $UV_ENV_FILE
  echo "export UV_NO_CONFIG=1" >> $UV_ENV_FILE
  echo "export UV_FROZEN=1" >> $UV_ENV_FILE
  echo "export UV_PROJECT_ENVIRONMENT=<path-to-project-venv>" >> $UV_ENV_FILE
  echo "export UV_PROJECT=<path-to-project>" >> $UV_ENV_FILE
  ```
  As a special `uv` case, you need to redirect `UV_CACHE_DIR` to a non-mounted path
  on the container (eg `/opt/uv_cache`), and after you're done installing stuff,
  remove that folder to keep containers small in size.

## Build containers for your OpenFOAM-based projects

1. Add your project to the configuration file.
2. Write a [definition file](https://apptainer.org/docs/user/main/definition_files.html) for your project.
3. Run `hpctainers` to build the containers.

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
      definition: projects/test.def # This is always relative to the current working directory
      build_args:
        branch:
          - master
          #- dev
```

`hpcTainers` will then create `containers/projects/test-master.sif` for you.

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
  - This allows users to run `apptainer run container.sif info` to get the contents of `apps.json`
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
apptainer run containers/projects/test-master.sif info
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
which can be queried with `jq` (or by issuing the info command from the container).

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

It's important to understand that hpcTainers will always generate containers with MPI support
as a first layer, then generate the basic framework container on top of that.

> [!IMPORTANT]
> Although definition files leveraging `spack` will be generally shorter and easier to maintain, the resulting
> containers will be much larger than using distribution package managers. Also, at the time of writing,
> `spack` doesn't allow for easy switching of the underlying distribution as random installation errors
> arise for the same definition file if you base it on ubuntu and centos 7 images.

## Container Testing

```bash
# Build containers and run tests
uvx hpctainers --test

# Run tests only (no building)
uvx hpctainers --test-only
```

1. **Command Execution Tests**
   - Run commands inside containers
   - Validate exit codes and output patterns

2. **File Existence Tests**
   - Check if critical files exist
   - Validate file paths

3. **Version Check Tests**
   - Extract and validate software versions
   - Pattern matching on command output

4. **Metadata Tests**
   - Inspect SIF labels
   - Validate container metadata

5. **Content Tests**
   - Check file contents
   - Pattern matching inside files

Currently, tests run basic validation (e.g., `/apps.json` existence) by default.
For custom tests, the infrastructure is ready for configuration in `config.yaml`:

```yaml
testing:
  enabled: false
  fail_fast: true
  tests:
    - type: command
      name: verify_hpctoolkit
      command: "hpcrun --version"
      expect_success: true
      severity: error  # error, warning, or info

    - type: file_exists
      name: check_apps_json
      path: "/apps.json"
      severity: error

    - type: version
      name: check_openmpi
      command: "mpirun --version"
      expect_pattern: "4\\.1\\.5"
```

## MPI Testing

```bash
# Run MPI tests after building
uvx hpctainers --mpi-test
```

1. **MPI Compatibility**
   - Checks host MPI vs container MPI versions
   - Major.minor version compatibility

2. **Hybrid MPI Mode**
   - Host MPI + container executable
   - Tests `mpirun -n 2 apptainer run --sharens container.sif command`

3. **Containerized MPI**
   - Fully containerized MPI execution
   - Tests `apptainer run container.sif 'mpirun -n 2 command'`

## Security Scanning

Install either Trivy (recommended) or Grype

```bash
# Scan containers (warning only, doesn't fail build)
hpctainers --security-scan

# Fail build on critical vulnerabilities
hpctainers --security-scan --fail-on-critical

# Use Grype instead of Trivy
hpctainers --security-scan --security-scanner grype
```

A JSON report will then include:
- Vulnerability summary by severity
- Detailed CVE information
- Package versions (installed vs fixed)
- CVE descriptions and CVSS scores

## Size Analysis

```bash
# Analyze container sizes
hpctainers --analyze-size
```

1. **Total Container Size**
   - Overall .sif file size
   - Size in MB/GB

2. **Component Breakdown**
   - Size of `/opt`, `/usr`, `/var`
   - Percentage of total size
   - Note: `/tmp` is not analyzed as it's bind-mounted from the host by default

3. **SIF Structure**
   - Internal SIF objects and their sizes
   - Analyzed with `apptainer sif list`

4. **Package Count**
   - Number of installed packages
   - Supports Debian/Ubuntu (dpkg) and RHEL (rpm)

## Report Generation

All features generate JSON reports in the `reports/` directory (configurable with `--report-dir`):

```
reports/
├── hpctoolkit-report.json      # Aggregate report
├── hpctoolkit-security.json    # Security scan details
├── hpctoolkit-size.json        # Size analysis details
└── summary-report.json         # Multi-container summary
```

### Report Structure

**Container Report** (`<container>-report.json`):
```json
{
  "container_name": "hpctoolkit",
  "container_path": "containers/basic/hpctoolkit.sif",
  "report_generated": "2025-11-08T12:00:00",
  "tests": { ... },
  "security": { ... },
  "size_analysis": { ... },
  "mpi_tests": { ... }
}
```

---

## Configuration Reference

### Basic Containers

Define base HPC containers with OS, MPI, and framework layers:

```yaml
containers:
  basic:
    container-name:
      os:
        distro: ubuntu          # Base OS (ubuntu, debian, centos, etc.)
        version: 24.04          # OS version
      mpi:
        implementation: openmpi # MPI implementation (openmpi, mpich, intelmpi)
        version: 4.1.5          # MPI version
      framework:
        definition: com-openfoam  # Framework definition file (without .def)
        version: 2312           # Framework version
```

**Layered Frameworks** - Install multiple frameworks in sequence:

```yaml
containers:
  basic:
    container-name:
      os:
        distro: ubuntu
        version: 24.04
      mpi:
        implementation: openmpi
        version: 4.1.5
      framework:
        - definition: com-openfoam
          version: 2312
        - definition: hpctoolkit
          version: 2024.01.99-next
```

### Project Containers

Build application containers on top of basic containers:

```yaml
containers:
  projects:
    project-name:
      base_container: container-name  # Must match a basic container name
      definition: projects/test.def   # Path to definition file (relative to CWD)
      build_args:                     # Optional: build argument variants
        branch:
          - master
          - dev
        mode:
          - debug
          - optimized
```

**Build Arguments**:
- Creates multiple container variants (e.g., `project-name-master.sif`, `project-name-dev.sif`)
- Available as `{{ BRANCH }}`, `{{ MODE }}` (uppercase) in definition files
- All basic container arguments also available: `{{ OS_DISTRO }}`, `{{ MPI_VERSION }}`, etc.

### Extra Basics

Load custom definition files from external sources:

```yaml
containers:
  extra_basics: /path/to/definitions  # Local path
  # OR
  extra_basics: https://github.com/user/repo  # Git repository

  basic:
    custom-container:
      mpi:
        implementation: custom_mpi  # Looks for custom_mpi.def in extra_basics/basic/
```

**Requirements**:
- Must contain a `basic/` subdirectory with `.def` files
- Definition files follow same structure as built-in definitions
- Can be used for both MPI and framework definitions

### Pull Configuration

Control container registry pulling behavior:

```yaml
pull:
  enabled: true                    # Try pulling before building
  registry: ghcr.io               # Container registry URL
  namespace: foamscience          # Registry namespace/organization
  fallback_to_build: true         # Build if pull fails
  containers:
    - container-name              # List of containers to pull
    - another-container
```

**Default Behavior**:
- Attempts to pull containers from registry first
- Falls back to building if pull fails
- Useful for CI/CD and reproducible builds

### Build Options

Global build settings:

```yaml
build:
  parallel: true                  # Build containers in parallel (default: true)
  max_workers: 4                  # Maximum parallel builds (default: CPU count)
  cache_enabled: true             # Use build cache (default: true)
  output_dir: containers          # Output directory (default: containers)
```

### Security Policy

```yaml
security:
  enabled: false              # Disabled by default
  scanner: trivy             # or grype
  fail_on_critical: false    # Fail build on critical CVEs
  fail_on_high: false        # Fail build on high CVEs
  ignore_unfixed: true       # Ignore vulnerabilities without fixes
  report_path: security-reports/
```

### Testing Configuration

```yaml
testing:
  enabled: false
  fail_fast: true            # Stop on first failure
  timeout: 300              # Default timeout per test
  tests:
    - type: command
      name: test_name
      command: "command to run"
      expect_success: true
      expect_pattern: "regex"  # Optional
      severity: error        # error, warning, info
```

### Complete Configuration Example

A comprehensive configuration combining all features:

```yaml
# Container definitions
containers:
  # Load custom definitions from external source
  extra_basics: https://github.com/FoamScience/spack-apptainer-containers

  # Basic containers with layered frameworks
  basic:
    openfoam-hpctoolkit:
      os:
        distro: ubuntu
        version: 24.04
      mpi:
        implementation: openmpi
        version: 4.1.5
      framework:
        - definition: com-openfoam
          version: 2312
        - definition: hpctoolkit
          version: 2024.01.99-next

  # Project containers with build variants
  projects:
    my-app:
      base_container: openfoam-hpctoolkit
      definition: projects/my-app.def
      build_args:
        branch:
          - master
          - dev
        mode:
          - optimized
          - debug

# Pull configuration
pull:
  enabled: true
  registry: ghcr.io
  namespace: foamscience
  fallback_to_build: true
  containers:
    - openfoam-hpctoolkit

# Build options
build:
  parallel: true
  max_workers: 4
  cache_enabled: true
  output_dir: containers

# Security scanning
security:
  enabled: true
  scanner: trivy
  fail_on_critical: true
  fail_on_high: false
  ignore_unfixed: true
  report_path: security-reports/

# Container testing
testing:
  enabled: true
  fail_fast: false
  timeout: 300
  tests:
    - type: file_exists
      name: check_apps_json
      path: "/apps.json"
      severity: error

    - type: command
      name: verify_openfoam
      command: "which foamExec"
      expect_success: true
      severity: error

    - type: version
      name: check_mpi_version
      command: "mpirun --version"
      expect_pattern: "4\\.1\\.5"
      severity: warning
```
