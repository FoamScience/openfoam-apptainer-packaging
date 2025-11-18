from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

from hpctainers.lib.config_parser import load_config
from hpctainers.lib.container_builder import ContainerBuilder
from hpctainers.lib.registry import ContainerRegistry
from hpctainers.lib.cache import BuildCache
from hpctainers.lib.dependency_graph import DependencyGraph, ContainerType
from hpctainers.lib.package_data import get_builtin_definitions_dir
from hpctainers.lib.parallel import ParallelBuilder, BuildTask
from hpctainers.lib.build_matrix import BuildMatrix
from hpctainers.lib.external_defs import load_external_definitions
from hpctainers.lib.testing import TestRunner, parse_test_config, TestSeverity, TestStatus
from hpctainers.lib.security_scanning import create_scanner, ScanPolicy, ScanStatus
from hpctainers.lib.size_analysis import SizeAnalyzer, save_analysis_report
from hpctainers.lib.mpi_testing import MPITester
from hpctainers.lib.reporting import ReportGenerator, ContainerReport
from hpctainers.lib.framework_discovery import discover_frameworks, format_framework_list


def setup_logging(verbose: bool = False, quiet: bool = False) -> None:
    """Configure logging.

    Args:
        verbose: Enable debug logging
        quiet: Suppress info logging
    """
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )


def check_apptainer_version() -> bool:
    """Check if Apptainer is installed and version >= 1.3.1.

    Returns:
        True if version is sufficient
    """
    try:
        result = subprocess.run(
            ['apptainer', '--version'],
            capture_output=True,
            text=True,
            check=True
        )
        version_str = result.stdout.strip().split()[-1]
        major, minor, patch = map(int, version_str.split('.')[:3])
        if (major, minor, patch) >= (1, 3, 1):
            logger.info(f"Apptainer version: {version_str}")
            return True
        else:
            logger.error(
                f"Apptainer version {version_str} is too old. "
                f"Required: >= 1.3.1"
            )
            return False

    except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as e:
        logger.error(f"Failed to check Apptainer version: {e}")
        return False


def build_dependency_graph(
    config_parser,
    project_variants: Dict[str, List]
) -> DependencyGraph:
    """Build dependency graph for all containers.

    Args:
        config_parser: Parsed configuration
        project_variants: Project build variants from BuildMatrix

    Returns:
        Dependency graph
    """
    graph = DependencyGraph()

    for mpi_name, os_config, mpi_config in config_parser.get_unique_mpi_configs():
        graph.add_node(
            mpi_name,
            ContainerType.MPI,
            depends_on=[],
            metadata={"os": os_config, "mpi": mpi_config}
        )
    for basic_name, basic_config in config_parser.get_basic_containers().items():
        mpi_container = basic_config.get_mpi_container_name()
        frameworks = basic_config.get_frameworks()
        if len(frameworks) > 1:
            current_base = mpi_container
            for idx, framework in enumerate(frameworks):
                is_last = (idx == len(frameworks) - 1)
                if is_last:
                    layer_name = basic_name
                else:
                    layer_name = f"{basic_name}-layer{idx + 1}"
                graph.add_node(
                    layer_name,
                    ContainerType.FRAMEWORK,
                    depends_on=[current_base],
                    metadata={"framework": framework, "basic_config": basic_config}
                )
                current_base = layer_name
        else:
            graph.add_node(
                basic_name,
                ContainerType.FRAMEWORK,
                depends_on=[mpi_container],
                metadata={"framework": frameworks[0], "basic_config": basic_config}
            )

    for project_name, variants in project_variants.items():
        project_config = config_parser.get_project_containers()[project_name]
        for variant in variants:
            container_name = variant.get_container_name()
            graph.add_node(
                container_name,
                ContainerType.PROJECT,
                depends_on=[project_config.base_container],
                metadata={
                    "project_config": project_config,
                    "variant": variant
                }
            )

    return graph


def generate_sample_config(output_path: Path) -> None:
    """Generate a sample configuration file.

    Args:
        output_path: Path to write the sample config
    """
    sample_config = """# containers section defines what containers to build
containers:

  # This is either a local path, or a Git repo URI
  # to load your own basic definition files; they can then be used in framework.definition below
  #extra_basics: /tmp/extrabasics

  # This section builds base containers in containers/basic
  basic:
    # Example: Build HPCToolkit container
    hpctoolkit:
      os:
        distro: ubuntu
        version: "24.04"
      mpi:
        implementation: openmpi
        version: "4.1.5"
      framework:
        definition: hpctoolkit
        version: 2024.01.1

    # Example: Build OpenFOAM container
    #openfoam:
    #  os:
    #    distro: ubuntu
    #    version: "24.04"
    #  mpi:
    #    implementation: openmpi
    #    version: "4.1.5"
    #  framework:
    #    - definition: com-openfoam
    #      version: 2312
    #      git_ref: default

  # This section builds project containers with build variants
  #projects:
  #  my-app:
  #    base: openfoam  # References basic container
  #    build_args:
  #      - name: SOLVER
  #        values: [simpleFoam, pimpleFoam]
  #      - name: OPTIMIZATION
  #        values: [O2, O3]

# pull section sets pull parameters
pull:
  try_to_pull: true  # Try to pull from registry before building
  protocol: "oras"   # oras, docker, or library
  scope: "ghcr.io/foamscience"

# OPTIONAL: Testing configuration (use --test flag to enable)
#testing:
#  enabled: false
#  fail_fast: true
#  tests:
#    - type: command
#      name: verify_version
#      command: "mpirun --version"
#      expect_success: true
#    - type: file_exists
#      name: check_apps_json
#      path: "/apps.json"

# OPTIONAL: Security scanning (use --security-scan flag to enable)
#security:
#  enabled: false
#  scanner: trivy  # or grype
#  fail_on_critical: false
#  fail_on_high: false
#  ignore_unfixed: true
#  report_path: security-reports/

# OPTIONAL: Size analysis (use --analyze-size flag to enable)
#size_analysis:
#  enabled: false
#  track_history: true
#  report_path: size-reports/
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(sample_config)

    logger.info(f"Generated sample configuration: {output_path}")
    logger.info(f"Sample configuration written to: {output_path}")
    logger.info(f"Edit the file and run:")
    logger.info(f"  uvx hpctainers --config {output_path}")


def generate_framework_template(output_path: Path):
    """Generate a template framework definition file.

    Args:
        output_path: Path where template should be written
    """
    template = """# ---------------------------------------------------------------------------
#
# Create [FRAMEWORK_NAME]-powered image
#
# Build
#   apptainer build myframework.sif my-framework.def
#
# Note
#   - Replace [FRAMEWORK_NAME] with your framework name
#   - Update package lists and build steps as needed
#   - Framework definitions build on top of MPI base containers
#
# ---------------------------------------------------------------------------
Bootstrap: localimage
From: containers/basic/{{ BASE_CONTAINER }}.sif

%arguments
    OS_DISTRO=ubuntu
    OS_VERSION=24.04
    MPI_IMPLEMENTATION=openmpi
    MPI_VERSION=4.1.5
    FRAMEWORK_VERSION=1.0.0
    FRAMEWORK_GIT_REF=default

%post -c /bin/bash
    DEBIAN_FRONTEND=noninteractive

    # Update package manager
    apt-get update

    # Install dependencies (customize for your framework)
    apt-get install -y --no-install-recommends \\
        build-essential \\
        cmake \\
        git \\
        wget \\
        ca-certificates \\
        pkg-config \\
        jq
        # Add your framework's dependencies here

    # Build and install your framework
    cd /opt
    # Example: git clone https://github.com/yourorg/yourframework.git
    # cd yourframework
    # mkdir build && cd build
    # cmake .. -DCMAKE_INSTALL_PREFIX=/opt/yourframework
    # make -j$(nproc)
    # make install

    # Update /apps.json with framework metadata
    # Replace 'myframework' with your framework name
    jq --arg app myframework --arg commit {{ FRAMEWORK_GIT_REF }} --arg branch {{ FRAMEWORK_GIT_REF }} \\
        '.[$app] |= if . == null then
        {
            "version": "{{ FRAMEWORK_VERSION }}",
            "branch": $branch,
            "commit": $commit,
            "source_script": "/opt/yourframework/setup.sh"
        }
        else . +
        {
            "version": "{{ FRAMEWORK_VERSION }}",
            "branch": $branch,
            "commit": $commit,
            "source_script": "/opt/yourframework/setup.sh"
        } end' /apps.json > /tmp/apps.json
    mv /tmp/apps.json /apps.json

    # Clean up build dependencies (optional - saves space)
    # apt-get autoremove -y build-essential cmake git

    # Clean apt cache
    apt-get clean
    rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

%environment
    #!/bin/bash
    # Source scripts from /apps.json (automatic from base image)
    jq -r '.. | .source_script? // empty' /apps.json | while read -r script; do
      if [[ -f "$script" ]]; then
        source "$script"
      fi
    done
    # Python virtual environments
    jq -r '.. | .python_env? // empty' /apps.json | while read -r script; do
      if [[ -d "$script" ]]; then
        source "$script/bin/activate"
      fi
    done
    # UV environment files
    jq -r '.. | .uv_env? // empty' /apps.json | while read -r script; do
      if [[ -f "$script" ]]; then
        source "$script"
      fi
    done

%runscript
    #!/bin/bash
    if [ $# -eq 0 ]; then
        /bin/bash
    else
        /bin/bash -c "$@"
    fi

%labels
    Author yourname@example.com
    Version {{ FRAMEWORK_VERSION }}
    Description YourFramework
    AppsFile /apps.json
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(template)

    logger.info(f"Generated framework template: {output_path}")
    logger.info(f"Framework template written to: {output_path}")
    logger.info(f"Edit the file to customize for your framework, then add to config.yaml:")
    logger.info(f"""
containers:
  basic:
    my-container:
      os:
        distro: ubuntu
        version: 24.04
      mpi:
        implementation: openmpi
        version: 4.1.5
      framework:
        definition: {output_path.stem}  # Without .def extension
        version: 1.0.0
""")


def generate_project_template(output_path: Path):
    """Generate a template project definition file.

    Args:
        output_path: Path where template should be written
    """
    template = """# ---------------------------------------------------------------------------
#
# Project-specific container
#
# Build
#   apptainer build myproject.sif myproject.def
#
# Note
#   - Project containers build on framework or MPI containers
#   - Used for application-specific customizations
#   - Can use build_args for parameterized builds
#
# ---------------------------------------------------------------------------
Bootstrap: localimage
From: {{ CONTAINERS_DIR }}/basic/{{ BASE_CONTAINER }}.sif

%arguments
    OS_VERSION=24.04
    MPI_VERSION=4.1.5
    # Add custom build arguments here

# %files
#     Copy local files into container (optional)
#     ./myapp /opt/myapp
#     ./config.yaml /etc/myapp/config.yaml

%post -c /bin/bash
    DEBIAN_FRONTEND=noninteractive

    # Install project-specific dependencies
    apt-get update
    apt-get install -y --no-install-recommends \\
        python3 \\
        python3-pip \\
        jq
        # Add project-specific packages

    # Install project code
    cd /opt
    # Example: Clone your project repository
    # git clone -b {{ GIT_BRANCH }} https://github.com/yourorg/yourproject.git
    # cd yourproject
    # pip3 install -r requirements.txt
    # python3 setup.py install

    # Create necessary directories
    mkdir -p /data /results

    # Update /apps.json with project metadata
    # Replace 'myproject' with your project name
    jq --arg app myproject \\
        '.[$app] |= if . == null then
        {
            "version": "{{ PROJECT_VERSION }}",
            "path": "/opt/myproject",
            "data_dir": "/data",
            "results_dir": "/results"
        }
        else . +
        {
            "version": "{{ PROJECT_VERSION }}",
            "path": "/opt/myproject",
            "data_dir": "/data",
            "results_dir": "/results"
        } end' /apps.json > /tmp/apps.json
    mv /tmp/apps.json /apps.json

    # Clean up
    apt-get clean
    rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

%runscript
    #!/bin/bash
    if [ $# -eq 0 ]; then
        /bin/bash
    else
        /bin/bash -c "$@"
    fi

%labels
    Author yourname@example.com
    Version {{ PROJECT_VERSION }}
    Description YourProject
    AppsFile /apps.json
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(template)

    logger.info(f"Generated project template: {output_path}")
    logger.info(f"Project template written to: {output_path}")
    logger.info(f"Edit the file to customize for your project, then add to config.yaml:")
    logger.info(f"""
containers:
  projects:
    my-project:
      base_container: ubuntu-24.04-openmpi-4.1.5-myframework
      definition: {output_path.stem}.def  # With .def extension for projects
      build_args:
        project_version:
          - "1.0.0"
          - "2.0.0"
        git_branch:
          - main
          - develop
""")


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    parser = argparse.ArgumentParser(
        description="Build Apptainer containers for HPC applications",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Most important flags group
    getting_started = parser.add_argument_group(
        'Getting Started',
        'Essential commands for configuration and templates'
    )
    getting_started.add_argument(
        '--config', '-c',
        type=Path,
        default=Path('config.yaml'),
        help='Path to configuration file (default: config.yaml)'
    )
    getting_started.add_argument(
        '--generate-config',
        type=Path,
        metavar='PATH',
        help='Generate a sample configuration file and exit'
    )
    getting_started.add_argument(
        '--list-frameworks',
        action='store_true',
        help='List available framework definitions (includes extra_basics if config provided) and exit'
    )
    getting_started.add_argument(
        '--create-framework',
        type=Path,
        metavar='PATH',
        help='Create a template framework definition file and exit'
    )
    getting_started.add_argument(
        '--create-project',
        type=Path,
        metavar='PATH',
        help='Create a template project definition file and exit'
    )
    getting_started.add_argument(
        '--shell', '-s',
        nargs='?',
        const='__REPL__',
        metavar='COMMAND',
        help='Run interactive shell (REPL) or execute a shell command (e.g., "container | from ubuntu")'
    )

    general = parser.add_argument_group('General Options')
    general.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose (debug) logging'
    )
    general.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Suppress informational output'
    )
    general.add_argument(
        '--force-rebuild', '--force', '-f',
        nargs='?',
        const='__ALL__',
        default=None,
        metavar='CONTAINERS',
        help='Force rebuild containers (optional: comma-separated names, default: all)'
    )
    general.add_argument(
        '--no-cache',
        action='store_true',
        help='Disable build cache (implies --force-rebuild)'
    )
    general.add_argument(
        '--no-pull',
        action='store_true',
        help='Disable registry pulls (always build locally)'
    )
    general.add_argument(
        '--parallel-jobs', '-j',
        type=int,
        default=None,
        help='Number of parallel build jobs (default: CPU count - 1)'
    )
    general.add_argument(
        '--sequential',
        action='store_true',
        help='Build sequentially (no parallelism)'
    )
    general.add_argument(
        '--graph-only',
        action='store_true',
        help='Generate dependency graph without building'
    )
    general.add_argument(
        '--graph-output',
        type=Path,
        default=Path('build-graph.svg'),
        help='Output path for dependency graph (default: build-graph.svg)'
    )
    general.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be built without actually building'
    )
    general.add_argument(
        '--test',
        action='store_true',
        help='Run tests after successful builds'
    )
    general.add_argument(
        '--test-only',
        action='store_true',
        help='Run tests on existing containers without building'
    )
    general.add_argument(
        '--mpi-test',
        action='store_true',
        help='Run MPI functionality tests'
    )
    general.add_argument(
        '--security-scan',
        action='store_true',
        help='Run security scanning (optional, disabled by default)'
    )
    general.add_argument(
        '--security-scanner',
        type=str,
        default='trivy',
        choices=['trivy', 'grype'],
        help='Security scanner to use (default: trivy)'
    )
    general.add_argument(
        '--fail-on-critical',
        action='store_true',
        help='Fail build on critical security vulnerabilities'
    )
    general.add_argument(
        '--analyze-size',
        action='store_true',
        help='Analyze container sizes and suggest optimizations'
    )
    general.add_argument(
        '--report-dir',
        type=Path,
        default=Path('reports'),
        help='Directory for reports (default: reports/)'
    )

    args = parser.parse_args()

    if args.generate_config:
        setup_logging(args.verbose, args.quiet)
        generate_sample_config(args.generate_config)
        return 0

    if args.create_framework:
        setup_logging(args.verbose, args.quiet)
        generate_framework_template(args.create_framework)
        return 0

    if args.create_project:
        setup_logging(args.verbose, args.quiet)
        generate_project_template(args.create_project)
        return 0

    # Handle shell mode
    if args.shell is not None:
        setup_logging(args.verbose, args.quiet)

        from hpctainers.shell import run_repl, run_command

        if args.shell == '__REPL__':
            # Interactive REPL mode
            logger.info("Starting interactive shell...")
            run_repl()
            return 0
        else:
            # One-liner command execution
            try:
                result = run_command(args.shell)
                if result is not None:
                    print(result)
                return 0
            except Exception as e:
                logger.error(f"Shell command failed: {e}")
                return 1

    if args.list_frameworks:
        setup_logging(args.verbose, args.quiet)
        builtin_defs_dir = get_builtin_definitions_dir()
        cache_dir = Path.cwd() / ".cache" / "external_defs"
        cache_dir.mkdir(parents=True, exist_ok=True)
        extra_dirs = []
        if args.config and args.config.exists():
            try:
                config_parser = load_config(args.config)
                extra_basics_paths = config_parser.get_extra_basics_paths()
                total_loaded = 0
                for extra_basics_path in extra_basics_paths:
                    count = load_external_definitions(extra_basics_path, cache_dir)
                    total_loaded += count
                if total_loaded > 0:
                    logger.info(f"Loaded {total_loaded} external definitions")
                if any(cache_dir.glob('*.def')):
                    extra_dirs.append(cache_dir)
            except Exception as e:
                logger.warning(f"Could not load config for extra frameworks: {e}")
                if args.verbose:
                    logger.exception("Full traceback:")

        frameworks = discover_frameworks(builtin_defs_dir, extra_dirs=extra_dirs)
        logger.info(format_framework_list(frameworks, verbose=args.verbose))
        return 0

    setup_logging(args.verbose, args.quiet)
    logger.info("=" * 60)
    logger.info("Container Build Mechanism")
    logger.info("=" * 60)

    if not check_apptainer_version():
        return 1
    try:
        logger.info(f"Loading configuration from {args.config}")
        config_parser = load_config(args.config)
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        if args.verbose:
            logger.exception("Configuration error details:")
        return 1

    original_dir = Path.cwd()
    containers_dir = original_dir / "containers"
    builtin_defs_dir = get_builtin_definitions_dir()
    external_defs_dir = original_dir / ".cache" / "external_defs"
    external_defs_dir.mkdir(parents=True, exist_ok=True)
    basic_defs_dir = builtin_defs_dir
    (containers_dir / "basic").mkdir(parents=True, exist_ok=True)
    (containers_dir / "projects").mkdir(parents=True, exist_ok=True)

    try:
        extra_basics_paths = config_parser.get_extra_basics_paths()
        total_defs_loaded = 0
        for extra_basics_path in extra_basics_paths:
            defs_loaded = load_external_definitions(extra_basics_path, external_defs_dir)
            total_defs_loaded += defs_loaded
        if total_defs_loaded > 0:
            logger.info(f"Loaded {total_defs_loaded} external definitions to {external_defs_dir}")
    except Exception as e:
        logger.error(f"Failed to load external definitions: {e}")
        if args.verbose:
            logger.exception("External definitions error:")
        return 1

    pull_config = config_parser.get_pull_config()
    registry = ContainerRegistry(
        protocol=pull_config.protocol,
        scope=pull_config.scope,
        try_to_pull=pull_config.try_to_pull and not args.no_pull
    )

    cache = None
    if not args.no_cache:
        cache = BuildCache()
        logger.info(f"Build cache enabled: {cache.cache_dir}")
    force_rebuild_containers = None
    if args.no_cache:
        force_rebuild_containers = '__ALL__'
    elif args.force_rebuild:
        if args.force_rebuild == '__ALL__':
            force_rebuild_containers = '__ALL__'
        else:
            force_rebuild_containers = set(name.strip() for name in args.force_rebuild.split(','))
            logger.info(f"Force rebuilding containers: {', '.join(sorted(force_rebuild_containers))}")

    projects = config_parser.get_project_containers()
    project_variants = BuildMatrix.generate_all_project_variants(projects)
    total_variants = BuildMatrix.get_total_variant_count(project_variants)
    logger.info(
        f"Configuration loaded: "
        f"{len(config_parser.get_basic_containers())} basic containers, "
        f"{len(projects)} projects ({total_variants} variants)"
    )

    logger.info("Building dependency graph...")
    graph = build_dependency_graph(config_parser, project_variants)
    if args.graph_only or args.graph_output:
        output_path = args.graph_output
        try:
            # Try using new visualization module
            from hpctainers.api.visualization import visualize_dependency_graph

            format = output_path.suffix[1:] if output_path.suffix else 'svg'
            logger.info(f"Generating dependency graph visualization ({format})...")

            try:
                rendered_path = visualize_dependency_graph(
                    graph,
                    output_path.with_suffix(''),
                    format=format
                )
                logger.info(f"Dependency graph saved to: {rendered_path}")
            except ImportError:
                # Fallback to old method if graphviz not available
                logger.warning("graphviz not available, using fallback export")
                if output_path.suffix == '.svg':
                    success = graph.export_svg(output_path)
                    if not success:
                        dot_path = output_path.with_suffix('.dot')
                        graph.export_dot(dot_path)
                        logger.info(f"Exported to {dot_path} (install graphviz for SVG)")
                else:
                    graph.export_dot(output_path)

            if args.graph_only:
                logger.info("Graph-only mode, exiting without building")
                return 0
        except Exception as e:
            logger.error(f"Failed to export graph: {e}")
            if args.graph_only:
                return 1

    try:
        build_order = graph.get_build_order()
        parallel_groups = graph.get_parallel_groups()
        logger.info(f"Build order computed: {len(build_order)} total containers")
        logger.info(f"Parallel groups: {len(parallel_groups)}")
    except ValueError as e:
        logger.error(f"Failed to compute build order: {e}")
        return 1

    if args.dry_run:
        logger.info("")
        logger.info("=== DRY RUN MODE ===")
        for group_idx, group in enumerate(parallel_groups, 1):
            logger.info("")
            logger.info(f"Group {group_idx} ({len(group)} containers):")
            for container in group:
                node = graph.nodes[container]
                logger.info(f"  - {container} ({node.container_type.value})")
        return 0

    builder = ContainerBuilder(
        containers_dir=containers_dir,
        basic_defs_dir=basic_defs_dir,
        original_dir=original_dir,
        registry=registry,
        cache=cache,
        force_rebuild=force_rebuild_containers,
        external_defs_dir=external_defs_dir
    )

    max_workers = 1 if args.sequential else args.parallel_jobs
    parallel_builder = ParallelBuilder(max_workers=max_workers)

    logger.info("")
    logger.info("=" * 60)
    logger.info("Starting container builds")
    logger.info("=" * 60)

    all_results = []
    total_built = 0
    total_skipped = 0
    total_failed = 0

    for group_idx, group in enumerate(parallel_groups, 1):
        logger.info("")
        logger.info(
            f"[Group {group_idx}/{len(parallel_groups)}] "
            f"Building {len(group)} containers..."
        )

        tasks = []

        for container_name in group:
            node = graph.nodes[container_name]
            if node.container_type == ContainerType.MPI:
                build_func = lambda name=container_name, node=node: builder.build_mpi_container(
                    name,
                    node.metadata["os"],
                    node.metadata["mpi"]
                )
            elif node.container_type == ContainerType.FRAMEWORK:
                build_func = lambda name=container_name, node=node: builder.build_framework_container(
                    name,
                    node.depends_on[0] if node.depends_on else "",
                    node.metadata["basic_config"].os,
                    node.metadata["basic_config"].mpi,
                    node.metadata["basic_config"].get_frameworks()
                )
            else:
                variant = node.metadata["variant"]
                project_config = node.metadata["project_config"]
                definition_file = original_dir / project_config.definition
                # Extract environment secrets from project config
                env_secrets = project_config.get_env_secrets() if hasattr(project_config, 'get_env_secrets') else {}
                build_func = lambda name=container_name, node=node, variant=variant, def_file=definition_file, secrets=env_secrets: builder.build_project_container(
                    name,
                    node.depends_on[0],
                    def_file,
                    variant.args,
                    env_secrets=secrets
                )

            tasks.append(BuildTask(
                container_name=container_name,
                build_func=build_func,
                depends_on=node.depends_on,
                metadata=node.metadata
            ))

        group_results = parallel_builder.build_parallel(tasks)
        all_results.extend(group_results)
        for result in group_results:
            if result.skipped:
                total_skipped += 1
            elif result.success:
                total_built += 1
            else:
                total_failed += 1
        if any(not r.success and not r.skipped for r in group_results):
            logger.error(f"Group {group_idx} had failures, stopping build")
            break

    logger.info("")
    logger.info("=" * 60)
    logger.info("Build Summary")
    logger.info("=" * 60)
    logger.info(f"Total containers: {len(all_results)}")
    logger.info(f"  Built: {total_built}")
    logger.info(f"  Skipped (cached/pulled/exists): {total_skipped}")
    logger.info(f"  Failed: {total_failed}")

    if total_failed > 0:
        logger.info("")
        logger.error("Failed containers:")
        for result in all_results:
            if not result.success and not result.skipped:
                logger.error(f"  - {result.container_name}")
                if result.error:
                    logger.error(f"    Error: {result.error}")
        return 1

    logger.info("")
    logger.info("✓ All containers built successfully!")

    if args.test or args.mpi_test or args.security_scan or args.analyze_size:
        logger.info("")
        logger.info("=" * 60)
        logger.info("Post-Build Validation")
        logger.info("=" * 60)

        report_gen = ReportGenerator(args.report_dir)
        containers_to_analyze = []

        for container_name in build_order:
            node = graph.nodes[container_name]
            if node.container_type == ContainerType.PROJECT:
                container_path = containers_dir / "projects" / f"{container_name}.sif"
            else:
                container_path = containers_dir / "basic" / f"{container_name}.sif"
            if container_path.exists():
                containers_to_analyze.append((container_name, container_path, node))

        validation_failed = False

        for container_name, container_path, node in containers_to_analyze:
            logger.info("")
            logger.info(f"Analyzing: {container_name}")

            container_report = ContainerReport(
                container_name=container_name,
                container_path=container_path
            )

            if args.test:
                if node.container_type in [ContainerType.FRAMEWORK, ContainerType.PROJECT]:
                    basic_config = None
                    if hasattr(node.metadata.get('basic_config', None), '__dict__'):
                        basic_config = node.metadata['basic_config']
                    try:
                        runner = TestRunner(container_path)
                        from lib.testing import TestDefinition, TestType
                        basic_tests = [
                            TestDefinition(
                                name="apps_json_exists",
                                test_type=TestType.FILE_EXISTS,
                                path="/apps.json"
                            )
                        ]
                        test_results = runner.run_all_tests(basic_tests)

                        passed = sum(1 for r in test_results if r.status == TestStatus.PASSED)
                        failed = sum(1 for r in test_results if r.status == TestStatus.FAILED)

                        logger.info(f"  Tests: {passed} passed, {failed} failed")

                        container_report.test_results = {
                            "results": [
                                {
                                    "test_name": r.test_name,
                                    "status": r.status.value,
                                    "message": r.message,
                                    "duration_s": r.duration_s
                                }
                                for r in test_results
                            ]
                        }

                        if failed > 0:
                            validation_failed = True

                    except Exception as e:
                        logger.error(f"  Test execution failed: {e}")

            if args.mpi_test and node.container_type == ContainerType.FRAMEWORK:
                try:
                    mpi_tester = MPITester(container_path)
                    mpi_results = mpi_tester.run_comprehensive_mpi_tests()
                    logger.info(f"  MPI Tests: {mpi_results['summary']}")
                    container_report.mpi_tests = mpi_results
                    if not mpi_results['summary']['all_tests_passed']:
                        logger.warning(f"  Some MPI tests failed")
                except Exception as e:
                    logger.error(f"  MPI test execution failed: {e}")

            if args.security_scan:
                try:
                    policy = ScanPolicy(
                        fail_on_critical=args.fail_on_critical,
                        fail_on_high=False,
                        ignore_unfixed=True
                    )

                    scanner = create_scanner(args.security_scanner, policy)
                    if not scanner.is_available():
                        logger.warning(f"  Security scanner '{args.security_scanner}' not available")
                    else:
                        logger.info(f"  Running security scan with {args.security_scanner}...")
                        scan_result = scanner.scan(container_path)
                        logger.info(f"  Vulnerabilities: "
                                   f"Critical={scan_result.get_severity_count('CRITICAL')}, "
                                   f"High={scan_result.get_severity_count('HIGH')}, "
                                   f"Medium={scan_result.get_severity_count('MEDIUM')}, "
                                   f"Low={scan_result.get_severity_count('LOW')}")
                        from lib.security_scanning import save_scan_report, Severity
                        report_path = args.report_dir / f"{container_name}-security.json"
                        save_scan_report(scan_result, report_path)
                        container_report.security_scan = {
                            "scanner": scan_result.scanner,
                            "status": scan_result.status.value,
                            "summary": scan_result.summary,
                            "total_vulnerabilities": scan_result.total_vulnerabilities(),
                            "error_message": scan_result.error_message
                        }
                        if scan_result.status == ScanStatus.POLICY_VIOLATION:
                            logger.error(f"  Security policy violation: {scan_result.error_message}")
                            validation_failed = True

                except Exception as e:
                    logger.error(f"  Security scan failed: {e}")

            if args.analyze_size:
                try:
                    analyzer = SizeAnalyzer(container_path)
                    analysis = analyzer.analyze()
                    logger.info(f"  Size: {analysis.total_mb:.2f} MB")
                    high_priority_suggestions = [
                        s for s in analysis.optimization_suggestions
                        if s.priority == "high"
                    ]

                    if high_priority_suggestions:
                        potential_savings = sum(s.potential_savings_mb for s in high_priority_suggestions)
                        logger.info(f"  Optimization potential: {potential_savings:.1f} MB")

                    report_path = args.report_dir / f"{container_name}-size.json"
                    save_analysis_report(analysis, report_path)

                    container_report.size_analysis = {
                        "size": {
                            "total_bytes": analysis.total_bytes,
                            "total_mb": analysis.total_mb,
                            "total_gb": analysis.total_gb
                        },
                        "component_breakdown": [
                            {
                                "path": c.path,
                                "size_mb": c.size_mb,
                                "percent": c.percent
                            }
                            for c in analysis.component_breakdown
                        ],
                        "optimization_suggestions": [
                            {
                                "category": s.category,
                                "description": s.description,
                                "potential_savings_mb": s.potential_savings_mb,
                                "priority": s.priority
                            }
                            for s in analysis.optimization_suggestions
                        ]
                    }

                except Exception as e:
                    logger.error(f"  Size analysis failed: {e}")

            if any([container_report.test_results, container_report.security_scan,
                   container_report.size_analysis, container_report.mpi_tests]):
                report_gen.generate_container_report(container_report)

        if validation_failed:
            logger.error("\n✗ Validation failed for one or more containers")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
