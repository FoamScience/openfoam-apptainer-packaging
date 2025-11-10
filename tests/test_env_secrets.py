"""Tests for environment secrets functionality."""

import os
import pytest
from hpctainers.api import dag
from hpctainers.lib.config_parser import ProjectContainerConfig


class TestEnvironmentSecrets:
    """Test environment secrets across all interfaces."""

    def test_with_env_secret_method(self):
        """Test with_env_secret() method."""
        container = (
            dag.container("test")
            .from_("ubuntu:24.04")
            .with_env_secret("github_token", "GITHUB_TOKEN")
            .with_env_secret("api_key", "API_KEY")
        )

        # Check that env_secrets are tracked
        assert container.env_secrets == {
            "github_token": "GITHUB_TOKEN",
            "api_key": "API_KEY"
        }

    def test_to_definition_with_env_secrets(self):
        """Test that env secrets appear in definition correctly."""
        container = (
            dag.container("test")
            .from_("ubuntu:24.04")
            .with_env_secret("token", "MY_TOKEN")
            .with_exec(["echo", "test"])
        )

        definition = container.to_definition()

        # Should include container-specific sourcing logic
        assert "/tmp/hpctainers_build_env_test.sh" in definition
        assert "source \"/tmp/hpctainers_build_env_test.sh\"" in definition
        assert "rm -f /tmp/hpctainers_build_env_test.sh" in definition

        # Should have cleanup
        assert "Final cleanup" in definition

    def test_to_definition_without_env_secrets(self):
        """Test that definition works without env secrets."""
        container = (
            dag.container("test")
            .from_("ubuntu:24.04")
            .with_exec(["echo", "test"])
        )

        definition = container.to_definition()

        # Should NOT include env secrets logic
        assert "hpctainers_build_env.sh" not in definition

    def test_yaml_config_get_env_secrets(self):
        """Test extracting env secrets from YAML config."""
        config = ProjectContainerConfig(
            base_container="ubuntu-24.04-openmpi-4.1.5",
            definition="test",
            build_args={
                "env_github_secret": ["GITHUB_TOKEN"],
                "ENV_API_KEY": ["MY_API_KEY"],
                "branch": ["main", "dev"],
                "version": ["1.0"]
            }
        )

        # Extract env secrets
        env_secrets = config.get_env_secrets()
        assert env_secrets == {
            "github_secret": "GITHUB_TOKEN",
            "API_KEY": "MY_API_KEY"
        }

        # Extract regular build args
        regular_args = config.get_regular_build_args()
        assert regular_args == {
            "branch": ["main", "dev"],
            "version": ["1.0"]
        }
        assert "env_github_secret" not in regular_args
        assert "ENV_API_KEY" not in regular_args

    def test_yaml_config_no_env_secrets(self):
        """Test YAML config without env secrets."""
        config = ProjectContainerConfig(
            base_container="ubuntu-24.04-openmpi-4.1.5",
            definition="test",
            build_args={
                "branch": ["main"],
                "version": ["1.0"]
            }
        )

        env_secrets = config.get_env_secrets()
        assert env_secrets == {}

        regular_args = config.get_regular_build_args()
        assert regular_args == {
            "branch": ["main"],
            "version": ["1.0"]
        }

    def test_yaml_config_env_prefix_case_insensitive(self):
        """Test that both env_ and ENV_ prefixes work."""
        config = ProjectContainerConfig(
            base_container="test",
            definition="test",
            build_args={
                "env_lowercase": ["VAR1"],
                "ENV_UPPERCASE": ["VAR2"],
                "Env_MixedCase": ["VAR3"]  # This won't match (only env_ and ENV_)
            }
        )

        env_secrets = config.get_env_secrets()

        # Only env_ and ENV_ prefixes should match
        assert "lowercase" in env_secrets
        assert "UPPERCASE" in env_secrets
        assert "Env_MixedCase" not in env_secrets

    def test_method_chaining_with_env_secrets(self):
        """Test that env secrets work with method chaining."""
        container = (
            dag.container("chained")
            .from_("ubuntu:24.04")
            .with_env_variable("PUBLIC_VAR", "public_value")
            .with_env_secret("secret_var", "SECRET_TOKEN")
            .with_exec(["echo", "$PUBLIC_VAR $SECRET_TOKEN"])
        )

        # Should have both regular env vars and secrets
        assert container.env_vars == {"PUBLIC_VAR": "public_value"}
        assert container.env_secrets == {"secret_var": "SECRET_TOKEN"}

        # Definition should handle both
        definition = container.to_definition()
        assert "export PUBLIC_VAR=public_value" in definition
        assert "hpctainers_build_env_chained.sh" in definition

    def test_multiple_container_types_with_secrets(self):
        """Test env secrets with different container types."""
        # Simple container
        simple = (
            dag.container("simple")
            .from_("ubuntu:24.04")
            .with_env_secret("token", "TOKEN")
        )
        simple_def = simple.to_definition()
        assert "hpctainers_build_env_simple.sh" in simple_def

        # MPI container
        mpi = (
            dag.container("mpi")
            .from_("ubuntu:24.04")
            .with_mpi("openmpi", "4.1.5")
            .with_env_secret("token", "TOKEN")
        )
        mpi_def = mpi.to_definition()
        assert "hpctainers_build_env_mpi.sh" in mpi_def

        # Project container
        project = (
            dag.container("project")
            .from_("ubuntu:24.04")
            .with_mpi("openmpi", "4.1.5")
            .with_framework("test", "1.0")
            .with_env_secret("token", "TOKEN")
        )
        project_def = project.to_definition()
        assert "hpctainers_build_env_project.sh" in project_def


class TestEnvironmentSecretsIntegration:
    """Integration tests for environment secrets (require actual environment)."""

    def test_env_secret_with_actual_env_var(self, monkeypatch):
        """Test that actual environment variables can be used."""
        # Set a test environment variable
        monkeypatch.setenv("TEST_SECRET_TOKEN", "test_value_12345")

        container = (
            dag.container("test-env")
            .from_("ubuntu:24.04")
            .with_env_secret("test_token", "TEST_SECRET_TOKEN")
        )

        # Verify it's tracked
        assert container.env_secrets == {"test_token": "TEST_SECRET_TOKEN"}

        # Definition should be generated correctly with container-specific path
        definition = container.to_definition()
        assert "hpctainers_build_env_test-env.sh" in definition

    def test_missing_env_var_warning(self, monkeypatch):
        """Test that missing environment variables generate warnings."""
        # Ensure the env var is NOT set
        monkeypatch.delenv("NONEXISTENT_VAR", raising=False)

        container = (
            dag.container("test-missing")
            .from_("ubuntu:24.04")
            .with_env_secret("missing", "NONEXISTENT_VAR")
        )

        # Should still work, but builder will warn at build time
        assert container.env_secrets == {"missing": "NONEXISTENT_VAR"}
