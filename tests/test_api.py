"""Tests for container-as-code API."""

import pytest
from pathlib import Path

from hpctainers.api import dag, function, container_to_yaml


class TestContainerAPI:
    """Test Container API methods."""

    def test_create_container(self):
        """Test creating a basic container."""
        container = dag.container()
        assert container is not None
        assert container.name is not None

    def test_from_method(self):
        """Test from_() method."""
        container = dag.container().from_("ubuntu:24.04")
        assert container.base_image == "ubuntu:24.04"

    def test_with_exec(self):
        """Test with_exec() method."""
        container = (
            dag.container()
            .from_("ubuntu:24.04")
            .with_exec(["apt-get", "update"])
        )
        assert len(container.post_commands) == 1
        assert container.post_commands[0] == ["apt-get", "update"]

    def test_with_env_variable(self):
        """Test with_env_variable() method."""
        container = (
            dag.container()
            .from_("ubuntu:24.04")
            .with_env_variable("LANG", "C.UTF-8")
        )
        assert container.env_vars["LANG"] == "C.UTF-8"

    def test_with_mpi(self):
        """Test with_mpi() method."""
        container = (
            dag.container()
            .from_("ubuntu:24.04")
            .with_mpi("openmpi", "4.1.5")
        )
        assert container.mpi_impl == "openmpi"
        assert container.mpi_version == "4.1.5"

    def test_with_framework(self):
        """Test with_framework() method."""
        container = (
            dag.container()
            .from_("ubuntu:24.04")
            .with_mpi("openmpi", "4.1.5")
            .with_framework("openfoam", "v2406")
        )
        assert len(container.frameworks) == 1
        assert container.frameworks[0]["definition"] == "openfoam"
        assert container.frameworks[0]["version"] == "v2406"

    def test_method_chaining(self):
        """Test method chaining."""
        container = (
            dag.container()
            .from_("ubuntu:24.04")
            .with_exec(["apt-get", "update"])
            .with_env_variable("LANG", "C.UTF-8")
            .with_exec(["apt-get", "install", "-y", "vim"])
        )
        assert container.base_image == "ubuntu:24.04"
        assert len(container.post_commands) == 2
        assert "LANG" in container.env_vars


class TestDecorators:
    """Test function decorators."""

    def test_function_decorator(self):
        """Test @function decorator."""
        @function
        def test_container():
            return dag.container().from_("alpine:latest")

        container = test_container()
        assert container.base_image == "alpine:latest"
        assert hasattr(test_container, '__hpctainers_function__')

    def test_function_with_args(self):
        """Test @function with arguments."""
        @function
        def parameterized_container(base: str = "ubuntu:24.04"):
            return dag.container().from_(base)

        container1 = parameterized_container()
        assert container1.base_image == "ubuntu:24.04"

        container2 = parameterized_container("alpine:latest")
        assert container2.base_image == "alpine:latest"


class TestTemplateGeneration:
    """Test template generation functionality."""

    def test_create_framework_template(self, tmp_path):
        """Test creating framework template."""
        output = tmp_path / "my-framework.def"
        result = dag.create_framework_template(output)

        assert result == output
        assert output.exists()
        assert output.is_file()

        # Check template contains expected sections
        content = output.read_text()
        assert "Bootstrap: localimage" in content
        assert "%arguments" in content
        assert "%post" in content
        assert "FRAMEWORK_VERSION" in content
        # Check for /apps.json handling
        assert "jq" in content
        assert "/apps.json" in content

    def test_create_project_template(self, tmp_path):
        """Test creating project template."""
        output = tmp_path / "my-project.def"
        result = dag.create_project_template(output)

        assert result == output
        assert output.exists()
        assert output.is_file()

        # Check template contains expected sections
        content = output.read_text()
        assert "Bootstrap: localimage" in content
        assert "%arguments" in content
        assert "%post" in content
        assert "BASE_CONTAINER" in content
        # Check for /apps.json handling
        assert "jq" in content
        assert "/apps.json" in content

    def test_list_available_frameworks(self):
        """Test listing available frameworks."""
        frameworks = dag.list_available_frameworks()

        # Should return a list
        assert isinstance(frameworks, list)

        # Should be sorted
        assert frameworks == sorted(frameworks)

        # Should include common frameworks (if they exist)
        # This test is flexible - just checks the API works
        # Actual frameworks depend on builtin definitions

    def test_list_available_mpi(self):
        """Test listing available MPI implementations."""
        mpi_impls = dag.list_available_mpi()

        # Should return a list
        assert isinstance(mpi_impls, list)

        # Should include standard implementations
        assert "openmpi" in mpi_impls
        assert "mpich" in mpi_impls


class TestDefinitionExport:
    """Test definition file export from containers."""

    def test_simple_container_to_definition(self):
        """Test exporting simple container to definition."""
        container = (
            dag.container("test-simple")
            .from_("ubuntu:24.04")
            .with_exec(["apt-get", "update"])
            .with_env_variable("LANG", "C.UTF-8")
        )

        definition = container.to_definition()

        # Check bootstrap
        assert "Bootstrap: docker" in definition
        assert "From: ubuntu:24.04" in definition

        # Check post section
        assert "%post" in definition
        assert "apt-get update" in definition
        assert "export LANG=C.UTF-8" in definition

        # Check /apps.json
        assert "/apps.json" in definition

        # Check runscript and labels
        assert "%runscript" in definition
        assert "%labels" in definition
        assert "AppsFile /apps.json" in definition

    def test_mpi_container_to_definition(self):
        """Test exporting MPI container to definition."""
        container = (
            dag.container("test-mpi")
            .from_("ubuntu:24.04")
            .with_mpi("openmpi", "4.1.5")
        )

        definition = container.to_definition()

        # Check bootstrap (should be docker for MPI - it's the base layer)
        assert "Bootstrap: docker" in definition
        assert "From: ubuntu:24.04" in definition

        # Check arguments
        assert "%arguments" in definition
        assert "MPI_IMPLEMENTATION=openmpi" in definition
        assert "MPI_VERSION=4.1.5" in definition

        # Check /apps.json handling for MPI
        assert "jq" in definition
        assert "openmpi" in definition
        assert "/opt/ompi/bashrc" in definition

        # Check environment section
        assert "%environment" in definition
        assert "source_script" in definition

    def test_framework_container_to_definition(self):
        """Test exporting project container to definition."""
        container = (
            dag.container("test-project")
            .from_("ubuntu:24.04")
            .with_mpi("openmpi", "4.1.5")
            .with_framework("myframework", "1.0.0", "main")
        )

        definition = container.to_definition()

        # Check framework arguments
        assert "FRAMEWORK_VERSION=1.0.0" in definition
        assert "FRAMEWORK_GIT_REF=main" in definition

        # Project containers should bootstrap from localimage (framework parent)
        assert "Bootstrap: localimage" in definition

        # Project containers should NOT add framework to /apps.json (it's in parent)
        # (this is tricky to test without building, but we can check it doesn't have jq for framework)
        # For now, just verify basic structure is correct

        # Project containers should NOT have %environment section (inherited from parent)
        assert "%environment" not in definition

    def test_save_definition(self, tmp_path):
        """Test saving definition to file."""
        container = (
            dag.container("test-save")
            .from_("ubuntu:24.04")
            .with_exec(["echo", "test"])
        )

        output = tmp_path / "test.def"
        result = container.save_definition(output)

        assert result == output
        assert output.exists()
        assert output.is_file()

        # Verify content
        content = output.read_text()
        assert "Bootstrap: docker" in content
        assert "echo test" in content

    def test_container_type_detection(self):
        """Test automatic container type detection."""
        # Simple container
        simple = dag.container().from_("ubuntu:24.04")
        assert "Bootstrap: docker" in simple.to_definition()

        # MPI container - should use docker bootstrap (base layer)
        mpi = dag.container().from_("ubuntu:24.04").with_mpi("openmpi", "4.1.5")
        assert "Bootstrap: docker" in mpi.to_definition()
        assert "MPI_IMPLEMENTATION" in mpi.to_definition()
        # Should add MPI to /apps.json
        assert 'jq --arg app openmpi' in mpi.to_definition()

        # Project container - should use localimage bootstrap (parent is framework)
        # When with_framework is present, we're building a PROJECT container
        project = (
            dag.container()
            .from_("ubuntu:24.04")
            .with_mpi("openmpi", "4.1.5")
            .with_framework("test", "1.0")
        )
        assert "Bootstrap: localimage" in project.to_definition()
        assert "FRAMEWORK_VERSION" in project.to_definition()
        # Should NOT add MPI to /apps.json (it's in parent MPI container)
        assert 'jq --arg app openmpi' not in project.to_definition()
        # Should NOT add framework to /apps.json (it's in parent framework container)
        assert 'jq --arg app test' not in project.to_definition()
        # Should NOT have %environment section (inherited from parent)
        assert '%environment' not in project.to_definition()


class TestYAMLBridge:
    """Test YAML-Python bridge."""

    def test_container_to_yaml(self):
        """Test converting container to YAML."""
        container = (
            dag.container()
            .from_("ubuntu:24.04")
            .with_mpi("openmpi", "4.1.5")
        )

        yaml_str = container_to_yaml(container, "test-container")
        assert "test-container:" in yaml_str
        assert "distro: ubuntu" in yaml_str
        assert 'version: "24.04"' in yaml_str
        assert "implementation: openmpi" in yaml_str

    @pytest.mark.skipif(
        not Path("config.yaml").exists(),
        reason="config.yaml not found"
    )
    def test_load_yaml_config(self):
        """Test loading YAML config."""
        config = dag.load_yaml("config.yaml")
        containers = config.list_basic_containers()
        assert isinstance(containers, list)


class TestShellParser:
    """Test shell parser."""

    def test_parse_simple_pipeline(self):
        """Test parsing simple pipeline."""
        from hpctainers.shell.parser import parse_pipeline

        commands = parse_pipeline("container | from ubuntu:24.04")
        assert len(commands) == 2
        assert commands[0].name == "container"
        assert commands[1].name == "from"
        assert commands[1].args == ["ubuntu:24.04"]

    def test_parse_with_args(self):
        """Test parsing with arguments."""
        from hpctainers.shell.parser import parse_pipeline

        commands = parse_pipeline("container | from ubuntu:24.04 | with-mpi openmpi 4.1.5")
        assert len(commands) == 3
        assert commands[2].name == "with-mpi"
        assert commands[2].args == ["openmpi", "4.1.5"]

    def test_to_python_code(self):
        """Test converting to Python code."""
        from hpctainers.shell.parser import PipelineParser

        parser = PipelineParser()
        commands = parser.parse("container | from ubuntu:24.04")
        code = parser.to_python_code(commands)
        assert "dag.container()" in code
        assert ".from_(" in code
        assert "ubuntu:24.04" in code


class TestShellInterpreter:
    """Test shell interpreter."""

    def test_execute_simple_pipeline(self):
        """Test executing simple pipeline."""
        from hpctainers.shell.interpreter import ShellInterpreter

        interpreter = ShellInterpreter()
        result = interpreter.execute("container | from ubuntu:24.04")

        assert result is not None
        assert hasattr(result, 'base_image')
        assert result.base_image == "ubuntu:24.04"

    def test_execute_with_methods(self):
        """Test executing with multiple methods."""
        from hpctainers.shell.interpreter import ShellInterpreter

        interpreter = ShellInterpreter()
        result = interpreter.execute(
            "container | from ubuntu:24.04 | with-exec apt-get update"
        )

        assert result is not None
        assert len(result.post_commands) > 0


class TestDAGVisualization:
    """Test DAG visualization."""

    def test_create_visualizer(self):
        """Test creating DAG visualizer."""
        from hpctainers.api import DAGVisualizer

        visualizer = DAGVisualizer()
        assert visualizer is not None
        assert len(visualizer.nodes) == 0
        assert len(visualizer.edges) == 0

    def test_add_nodes(self):
        """Test adding nodes."""
        from hpctainers.api import DAGVisualizer

        visualizer = DAGVisualizer()
        visualizer.add_node("node1", "mpi")
        visualizer.add_node("node2", "framework")

        assert len(visualizer.nodes) == 2
        assert "node1" in visualizer.nodes
        assert visualizer.nodes["node1"]["type"] == "mpi"

    def test_add_edges(self):
        """Test adding edges."""
        from hpctainers.api import DAGVisualizer

        visualizer = DAGVisualizer()
        visualizer.add_node("base", "mpi")
        visualizer.add_node("app", "framework")
        visualizer.add_edge("base", "app")

        assert len(visualizer.edges) == 1
        assert ("base", "app") in visualizer.edges

    def test_to_mermaid(self):
        """Test Mermaid export."""
        from hpctainers.api import DAGVisualizer

        visualizer = DAGVisualizer()
        visualizer.add_node("base", "mpi")
        visualizer.add_node("app", "framework")
        visualizer.add_edge("base", "app")

        mermaid = visualizer.to_mermaid()
        assert "graph TD" in mermaid
        assert "base" in mermaid
        assert "app" in mermaid
        assert "-->" in mermaid

    def test_to_dot(self):
        """Test DOT export."""
        from hpctainers.api import DAGVisualizer

        visualizer = DAGVisualizer()
        visualizer.add_node("base", "mpi")
        visualizer.add_node("app", "framework")
        visualizer.add_edge("base", "app")

        dot = visualizer.to_dot()
        assert "digraph container_dag" in dot
        assert '"base"' in dot
        assert '"app"' in dot
        assert "->" in dot

    def test_get_build_order(self):
        """Test build order calculation."""
        from hpctainers.api import DAGVisualizer

        visualizer = DAGVisualizer()

        # Create a simple DAG
        # base -> app1
        # base -> app2
        visualizer.add_node("base", "mpi")
        visualizer.add_node("app1", "framework")
        visualizer.add_node("app2", "framework")
        visualizer.add_edge("base", "app1")
        visualizer.add_edge("base", "app2")

        build_order = visualizer.get_build_order()

        # Should have 2 stages
        assert len(build_order) == 2

        # First stage should have base
        assert "base" in build_order[0]

        # Second stage should have both apps (parallel)
        assert "app1" in build_order[1]
        assert "app2" in build_order[1]

    def test_clear(self):
        """Test clearing DAG."""
        from hpctainers.api import DAGVisualizer

        visualizer = DAGVisualizer()
        visualizer.add_node("node1", "mpi")
        visualizer.add_edge("node1", "node2")

        visualizer.clear()

        assert len(visualizer.nodes) == 0
        assert len(visualizer.edges) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
