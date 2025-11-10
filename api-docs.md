# Container-as-Code with hpctainers

hpctainers now supports **container-as-code** - a Dagger.io-inspired approach to building HPC containers programmatically using Python or an interactive shell.

<!-- mtoc-start:12ac786 -->

* [Three Ways to Build Containers](#three-ways-to-build-containers)
  * [1. YAML Configuration](#1-yaml-configuration)
  * [2. Python API](#2-python-api)
  * [3. Interactive Shell](#3-interactive-shell)
* [Quick Start](#quick-start)
* [Python API Reference](#python-api-reference)
  * [DAG Entry Points](#dag-entry-points)
  * [Container Methods](#container-methods)
    * [Core Operations](#core-operations)
    * [HPC-Specific Operations](#hpc-specific-operations)
    * [Build and Debug](#build-and-debug)
  * [Decorators](#decorators)
    * [@function](#function)
* [Interactive Shell Reference](#interactive-shell-reference)
  * [Starting the Shell](#starting-the-shell)
  * [Pipe Syntax](#pipe-syntax)
  * [Variables](#variables)
  * [Built-in Commands](#built-in-commands)
  * [Examples](#examples)
* [YAML-Python Bridge](#yaml-python-bridge)
  * [Load YAML in Python](#load-yaml-in-python)
  * [Convert Python to YAML](#convert-python-to-yaml)
  * [Call Python Functions from YAML](#call-python-functions-from-yaml)
* [Creating Custom Frameworks](#creating-custom-frameworks)
  * [NEW: Programmatic Definition Export](#new-programmatic-definition-export)
  * [Alternative: Template-Based Workflow](#alternative-template-based-workflow)
  * [Creating a Project Container](#creating-a-project-container)
  * [Framework Validation](#framework-validation)
  * [Discovering Available Frameworks](#discovering-available-frameworks)
* [Advanced Features](#advanced-features)
  * [Caching](#caching)
  * [Parallel Builds](#parallel-builds)
  * [Testing](#testing)
* [Examples](#examples-1)
* [Architecture](#architecture)
  * [Shared Infrastructure](#shared-infrastructure)
  * [Module Structure](#module-structure)
* [Backwards Compatibility](#backwards-compatibility)
* [Migration Guide](#migration-guide)
  * [From YAML to Python API](#from-yaml-to-python-api)
* [Comparison with Dagger](#comparison-with-dagger)
* [DAG Visualization](#dag-visualization)
  * [From CLI (YAML Configs)](#from-cli-yaml-configs)
  * [From Python API](#from-python-api)
  * [Visualize Existing Dependency Graph](#visualize-existing-dependency-graph)
  * [Export Formats](#export-formats)
  * [Requirements](#requirements)

<!-- mtoc-end:12ac786 -->

## Three Ways to Build Containers

### 1. YAML Configuration

Traditional declarative approach - still fully supported:

```yaml
containers:
  basic:
    foam-ubuntu:
      os:
        distro: ubuntu
        version: "24.04"
      mpi:
        implementation: openmpi
        version: "4.1.5"
      framework:
        definition: openfoam
        version: v2406
```

```bash
hpctainers --config config.yaml
```

### 2. Python API

Programmatic approach with fluent method chaining:

```python
from hpctainers.api import dag, function

# Simple container
container = (
    dag.container()
    .from_("ubuntu:24.04")
    .with_exec(["apt-get", "update"])
    .with_mpi("openmpi", "4.1.5")
    .with_framework("openfoam", "v2406")
    .build()
)

# Reusable functions
@function
def openmpi_container(version: str = "4.1.5"):
    return (
        dag.container()
        .from_("ubuntu:24.04")
        .with_mpi("openmpi", version)
    )
```

### 3. Interactive Shell

REPL with pipe-based syntax:

```bash
$ hpctainers --shell
hpctainers> container | from ubuntu:24.04 | with-mpi openmpi 4.1.5 | build
hpctainers> .help
hpctainers> .exit
```

## Quick Start

```python
from hpctainers.api import dag

# Create and build container
container = (
    dag.container()
    .from_("ubuntu:24.04")
    .with_exec(["apt-get", "update"])
    .with_exec(["apt-get", "install", "-y", "build-essential"])
    .build()
)

print(f"Container built: {container}")
```

```bash
# Start REPL
hpctainers --shell

# Or execute one-liner
hpctainers -s "container | from ubuntu:24.04 | with-exec apt-get update | build"
```

## Python API Reference

### DAG Entry Points

```python
from hpctainers.api import dag

# Create container
container = dag.container()

# Create directory
directory = dag.directory()

# Load YAML config
config = dag.load_yaml("config.yaml")

# Template generation (uses same templates as --create-framework/--create-project)
dag.create_framework_template("basic/my-framework.def")
dag.create_project_template("projects/my-app.def")

# Discovery
available_frameworks = dag.list_available_frameworks()
available_mpi = dag.list_available_mpi()
```

### Container Methods

#### Core Operations

- **`.from_(base_image)`** - Bootstrap from Docker image
  ```python
  .from_("ubuntu:24.04")
  ```

- **`.with_exec(cmd)`** - Execute command
  ```python
  .with_exec(["apt-get", "update"])
  .with_exec(["apt-get", "install", "-y", "vim"])
  ```

- **`.with_env_variable(name, value)`** - Set environment variable
  ```python
  .with_env_variable("LANG", "C.UTF-8")
  ```

- **`.with_file(path, content)`** - Add file
  ```python
  .with_file("/etc/motd", "Welcome to HPC container!")
  ```

- **`.with_directory(path, source)`** - Mount directory
  ```python
  .with_directory("/data", "/path/on/host")
  ```

#### HPC-Specific Operations

- **`.with_mpi(implementation, version)`** - Add MPI
  ```python
  .with_mpi("openmpi", "4.1.5")
  .with_mpi("mpich", "4.0.3")
  .with_mpi("intel-mpi", "2021.5")
  ```

- **`.with_framework(definition, version, git_ref)`** - Add HPC framework
  ```python
  .with_framework("openfoam", "v2406")
  .with_framework("foam-extend", "5.0", "main")
  ```

- **`.with_spack_env(packages)`** - Install Spack packages
  ```python
  .with_spack_env(["hdf5", "netcdf-c"])
  .with_spack_env("fftw")
  ```

- **`.with_build_tools(remove_after=True)`** - Add build tools
  ```python
  .with_build_tools(remove_after=True)  # Multi-stage build
  ```

#### Build and Debug

- **`.build(output=None)`** - Build container
  ```python
  path = container.build()
  path = container.build(Path("custom/output.sif"))
  ```

- **`.terminal(cmd=None)`** - Open interactive terminal
  ```python
  .terminal()  # Opens bash shell
  .terminal("/bin/sh")  # Custom shell
  ```

### Decorators

#### @function

Mark functions as reusable container builders:

```python
from hpctainers.api import function, dag

@function
def my_hpc_container(mpi_version: str = "4.1.5"):
    """Build HPC container with MPI."""
    return (
        dag.container()
        .from_("ubuntu:24.04")
        .with_mpi("openmpi", mpi_version)
    )

# Use it
container = my_hpc_container("4.1.6")
```

## Interactive Shell Reference

### Starting the Shell

```bash
# Interactive REPL
hpctainers --shell
hpctainers -s

# Execute command
hpctainers -s "container | from alpine | terminal"

# Run script file
hpctainers -s < build-script.sh
```

### Pipe Syntax

Commands are chained with `|` (pipe operator):

```bash
container | from ubuntu:24.04 | with-exec apt-get update | build
```

Translates to:

```python
dag.container().from_("ubuntu:24.04").with_exec(["apt-get", "update"]).build()
```

### Variables

Save results to variables:

```bash
$mpi = container | from ubuntu:24.04 | with-mpi openmpi 4.1.5
$foam = $mpi | with-framework openfoam v2406
$foam | build
```

### Built-in Commands

All built-in commands start with `.`:

- **`.help`** - Show help
- **`.list`** - List available methods
- **`.inspect <object>`** - Inspect object
- **`.vars`** - List variables
- **`.history`** - Show command history
- **`.exit`** - Exit shell (or Ctrl+D)

### Examples

```bash
# Basic container
hpctainers> container | from ubuntu:24.04 | build

# With MPI
hpctainers> container | from ubuntu | with-mpi openmpi 4.1.5 | build

# With framework
hpctainers> container | from ubuntu | with-mpi openmpi 4.1.5 | with-framework openfoam v2406 | build

# Interactive debugging
hpctainers> container | from alpine | with-exec apk add vim | terminal

# Using variables
hpctainers> $base = container | from ubuntu:24.04
hpctainers> $mpi = $base | with-mpi openmpi 4.1.5
hpctainers> $mpi | build

# Get help
hpctainers> .help
hpctainers> .list
hpctainers> .vars
```

## YAML-Python Bridge

Mix and match YAML configs with Python API!

### Load YAML in Python

```python
from hpctainers.api import dag

# Load YAML config
config = dag.load_yaml("config.yaml")

# List containers
containers = config.list_basic_containers()

# Get container as API object
container = config.get_basic_container("foam-ubuntu")

# Extend with Python API
extended = container.with_exec(["apt-get", "install", "-y", "vim"])
extended.build()
```

### Convert Python to YAML

```python
from hpctainers.api import dag, container_to_yaml

# Create with API
container = (
    dag.container()
    .from_("ubuntu:24.04")
    .with_mpi("openmpi", "4.1.5")
)

# Convert to YAML
yaml_str = container_to_yaml(container, "my-container")
print(yaml_str)
```

### Call Python Functions from YAML

Define reusable functions in Python:

```python
# my_builders.py
from hpctainers.api import function, dag

@function
def custom_mpi_container(mpi_version: str = "4.1.5"):
    return (
        dag.container()
        .from_("ubuntu:24.04")
        .with_mpi("openmpi", mpi_version)
    )
```

Reference from YAML:

```yaml
containers:
  basic:
    custom-mpi:
      python_function: "my_builders:custom_mpi_container"
      args:
        mpi_version: "4.1.6"
```

## Creating Custom Frameworks

### NEW: Programmatic Definition Export

**No more manual template editing!** Define containers programmatically and export to definition files:

```python
from hpctainers.api import dag

# 1. Define container using fluent API
container = (
    dag.container("my-framework")
    .from_("ubuntu:24.04")
    .with_mpi("openmpi", "4.1.5")
    .with_exec(["apt-get", "update"])
    .with_exec(["apt-get", "install", "-y", "build-essential", "git"])
    .with_exec(["git", "clone", "https://github.com/yourorg/yourframework.git", "/opt/yourframework"])
    .with_exec(["cd", "/opt/yourframework", "&&", "./configure", "&&", "make", "-j$(nproc)", "&&", "make", "install"])
)

# 2. Export to definition file (automatic /apps.json handling!)
container.save_definition("basic/my-framework.def")

# 3. Use it - the definition file matches existing format exactly
# Via YAML config OR build directly:
container.build()
```

**Key benefits:**
- ✅ No manual editing required
- ✅ Automatic /apps.json handling with jq
- ✅ Proper bootstrapping (docker vs localimage)
- ✅ Environment setup (%environment section)
- ✅ Definition file matches existing format exactly
- ✅ All API methods translate to proper definition sections

### Alternative: Template-Based Workflow

If you prefer templates, you can still use them:

1. **Generate template**:
```python
from hpctainers.api import dag

# Create template (same as hpctainers --create-framework)
dag.create_framework_template("basic/my-framework.def")
```

2. **Edit the template** - now includes /apps.json handling:
```bash
Bootstrap: localimage
From: containers/basic/{{ BASE_CONTAINER }}.sif

%post -c /bin/bash
    # Your framework installation steps
    cd /opt
    git clone https://github.com/yourorg/yourframework.git
    cd yourframework
    ./configure && make -j$(nproc) && make install

    # Update /apps.json (included in template)
    jq --arg app myframework --arg commit {{ FRAMEWORK_GIT_REF }} --arg branch {{ FRAMEWORK_GIT_REF }} \
        '.[$app] |= {...}' /apps.json > /tmp/apps.json
    mv /tmp/apps.json /apps.json
```

3. **Use the framework**:
```python
container = (
    dag.container()
    .from_("ubuntu:24.04")
    .with_mpi("openmpi", "4.1.5")
    .with_framework("my-framework", "1.0.0")  # Uses basic/my-framework.def
    .build()
)
```

### Creating a Project Container

1. **Generate template**:
```python
dag.create_project_template("projects/my-app.def")
```

2. **Edit and use via YAML config**:
```yaml
containers:
  basic:
    my-base:
      os: {distro: ubuntu, version: "24.04"}
      mpi: {implementation: openmpi, version: "4.1.5"}
      framework: {definition: my-framework, version: "1.0.0"}

  projects:
    my-app:
      base_container: my-base
      definition: projects/my-app.def
```

### Framework Validation

The API validates that framework definitions exist and provides helpful guidance:

```python
# If framework doesn't exist
container.with_framework("nonexistent", "1.0")
# WARNING: Framework definition 'nonexistent' not found in builtin definitions.
# To create a template: dag.create_framework_template('basic/nonexistent.def')
# Or use CLI: hpctainers --create-framework basic/nonexistent.def
```

### Discovering Available Frameworks

```python
# List all available frameworks
frameworks = dag.list_available_frameworks()
print(frameworks)  # ['openfoam', 'com-openfoam', 'foam-extend', 'hpctoolkit', ...]

# List available MPI implementations
mpis = dag.list_available_mpi()
print(mpis)  # ['openmpi', 'mpich', 'intel-mpi']
```

## Advanced Features

### Caching

All builds use the same caching system:

```python
from hpctainers.api import get_builder, reset_builder

# Configure builder
reset_builder(
    cache_enabled=True,
    try_pull=True,
    force_rebuild=False
)

# Build (cached automatically)
container.build()
```

### Parallel Builds

Use the dependency graph for parallel builds (YAML only currently):

```bash
hpctainers --config config.yaml --parallel-jobs 4
```

### Testing

```bash
# Run tests
pytest tests/test_api.py -v

# Run specific test
pytest tests/test_api.py::TestContainerAPI::test_with_mpi -v
```

## Examples

See the `examples/` directory:

- **`api_basic.py`** - Basic Python API usage
- **`api_hpc.py`** - HPC containers with @function
- **`yaml_bridge.py`** - YAML-Python integration
- **`custom_builders.py`** - Custom build functions
- **`shell_examples.sh`** - Shell command examples
- **`README.md`** - Detailed examples guide

## Architecture

### Shared Infrastructure

All three approaches (YAML, Python, Shell) share:

- **BuildCache** - Content-based caching with cascade invalidation
- **ContainerBuilder** - Apptainer build orchestration
- **ContainerRegistry** - Image registry pulls (ORAS, Docker)
- **DependencyGraph** - Dependency resolution and parallel builds

### Module Structure

```
src/hpctainers/
├── api/                      # Python API
│   ├── __init__.py
│   ├── container.py          # Container class
│   ├── dag.py                # DAG entry point
│   ├── decorators.py         # @function decorator
│   ├── builder.py            # Integration with build system
│   ├── types.py              # Type definitions
│   └── yaml_bridge.py        # YAML-Python bridge
├── shell/                    # Interactive shell
│   ├── __init__.py
│   ├── parser.py             # Pipe syntax parser
│   ├── interpreter.py        # Shell interpreter
│   ├── repl.py               # Interactive REPL
│   └── builtins.py           # Built-in commands
└── lib/                      # Existing infrastructure
    ├── config_parser.py      # YAML parsing
    ├── container_builder.py  # Build orchestration
    ├── cache.py              # Build cache
    └── ...
```

## Backwards Compatibility

**100% backwards compatible** - all existing YAML workflows continue to work unchanged:

```bash
# Existing workflows still work
hpctainers --config config.yaml
hpctainers --config config.yaml --force-rebuild
hpctainers --list-frameworks
```

The Python API and shell are **additive features** that don't break anything.

## Migration Guide

### From YAML to Python API

**YAML:**
```yaml
containers:
  basic:
    my-container:
      os: {distro: ubuntu, version: "24.04"}
      mpi: {implementation: openmpi, version: "4.1.5"}
      framework: {definition: openfoam, version: v2406}
```

**Python API:**
```python
from hpctainers.api import dag

container = (
    dag.container()
    .from_("ubuntu:24.04")
    .with_mpi("openmpi", "4.1.5")
    .with_framework("openfoam", "v2406")
    .build()
)
```

**Shell:**
```bash
container | from ubuntu:24.04 | with-mpi openmpi 4.1.5 | with-framework openfoam v2406 | build
```

## Comparison with Dagger

hpctainers' container-as-code is inspired by Dagger.io but adapted for HPC:

| Feature | Dagger | hpctainers |
|---------|--------|------------|
| API Style | Fluent/chaining | Fluent/chaining ✓ |
| Shell | Interactive REPL | Interactive REPL ✓ |
| Pipe Syntax | `container \| from \| exec` | `container \| from \| with-exec` ✓ |
| Caching | GraphQL DAG | Content-based cache ✓ |
| HPC Support | Generic containers | MPI, frameworks, Spack ✓ |
| Backend | BuildKit | Apptainer ✓ |
| Language | Go, Python, TS | Python ✓ |

## DAG Visualization

Visualize container build dependencies to understand and optimize your build process.

### From CLI (YAML Configs)

```bash
# Generate dependency graph without building
hpctainers --config config.yaml --graph-only

# Custom output format
hpctainers --config config.yaml --graph-output dag.png --graph-only
hpctainers --config config.yaml --graph-output dag.pdf --graph-only

# Build and also generate graph
hpctainers --config config.yaml --graph-output build-graph.svg
```

### From Python API

```python
from hpctainers.api import DAGVisualizer

# Create visualizer
visualizer = DAGVisualizer()

# Add nodes (containers)
visualizer.add_node("base-mpi", "mpi")
visualizer.add_node("openfoam", "framework")
visualizer.add_node("my-app", "project")

# Add dependencies
visualizer.add_edge("base-mpi", "openfoam")
visualizer.add_edge("openfoam", "my-app")

# Render to file (SVG, PNG, PDF)
visualizer.render("dag.svg", format="svg")

# Export as Mermaid diagram
mermaid = visualizer.to_mermaid()
print(mermaid)

# Export as DOT
dot = visualizer.to_dot()

# Get build order
build_order = visualizer.get_build_order()
for i, group in enumerate(build_order, 1):
    print(f"Stage {i}: {group}")  # Containers that can build in parallel
```

### Visualize Existing Dependency Graph

```python
from hpctainers.api import visualize_dependency_graph
from hpctainers.lib.dependency_graph import DependencyGraph

# Build dependency graph from YAML
# (normally done automatically by CLI)
graph = DependencyGraph()
# ... add nodes and edges ...

# Visualize it
visualize_dependency_graph(graph, "output.svg", format="svg")
```

### Export Formats

- **SVG** - Scalable vector graphics (default, best for documentation)
- **PNG** - Raster image (good for presentations)
- **PDF** - Portable document format (good for reports)
- **DOT** - Graphviz source (for custom processing)
- **Mermaid** - Text-based diagram (for Markdown/documentation)

### Requirements

DAG visualization requires graphviz:

```bash
pip install graphviz

# System graphviz (for rendering)
# Ubuntu/Debian:
sudo apt-get install graphviz

# macOS:
brew install graphviz
```

Without graphviz, you can still export DOT and Mermaid formats.
