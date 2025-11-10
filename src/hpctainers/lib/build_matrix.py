"""Build argument matrix generation.

Generates all combinations of build arguments for project containers,
replicating the Ansible build argument matrix behavior.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class BuildVariant:
    """Represents a single build variant with specific argument values."""

    project_name: str
    args: Dict[str, str]
    container_suffix: str

    def get_container_name(self) -> str:
        """Generate container name for this variant.

        Returns:
            Container name in format: <project>-<arg1>-<arg2>-...
            If no args, returns just the project name.

        Example:
            >>> variant = BuildVariant("test", {"branch": "master", "mode": "debug"}, "master-debug")
            >>> variant.get_container_name()
            'test-master-debug'
        """
        if self.container_suffix:
            return f"{self.project_name}-{self.container_suffix}"
        return self.project_name

    def get_build_args_list(self) -> List[str]:
        """Get build arguments as list of --build-arg flags.

        Returns:
            List of apptainer build arguments

        Example:
            >>> variant.get_build_args_list()
            ['--build-arg', 'BRANCH=master', '--build-arg', 'MODE=debug']
        """
        args_list = []
        for key, value in self.args.items():
            arg_key = key.upper()
            args_list.extend(['--build-arg', f'{arg_key}={value}'])
        return args_list


class BuildMatrix:
    """Generate Cartesian product of build arguments."""

    @staticmethod
    def generate_variants(
        project_name: str,
        build_args: Dict[str, List[str]]
    ) -> List[BuildVariant]:
        """Generate all build variants from build arguments.

        Args:
            project_name: Name of the project
            build_args: Dictionary mapping argument names to lists of values

        Returns:
            List of BuildVariant objects, one for each combination

        Example:
            >>> build_args = {"branch": ["master", "dev"], "mode": ["debug", "release"]}
            >>> variants = BuildMatrix.generate_variants("test", build_args)
            >>> len(variants)
            4
            >>> variants[0].get_container_name()
            'test-master-debug'
        """
        if not build_args:
            return [BuildVariant(project_name, {}, "")]

        sorted_keys = sorted(build_args.keys())

        value_lists = [build_args[key] for key in sorted_keys]
        combinations = list(itertools.product(*value_lists))

        variants = []
        for combo in combinations:
            args_dict = dict(zip(sorted_keys, combo))
            suffix = "-".join(str(value) for value in combo)
            variants.append(BuildVariant(project_name, args_dict, suffix))

        return variants

    @staticmethod
    def generate_all_project_variants(
        projects: Dict[str, 'ProjectContainerConfig']
    ) -> Dict[str, List[BuildVariant]]:
        """Generate variants for all projects.

        Args:
            projects: Dictionary of project configurations

        Returns:
            Dictionary mapping project names to lists of variants

        Example:
            >>> from hpctainers.lib.config_parser import ProjectContainerConfig
            >>> projects = {
            ...     "test": ProjectContainerConfig(
            ...         base_container="opencfd-openfoam",
            ...         definition="projects/test.def",
            ...         build_args={"branch": ["master", "dev"]}
            ...     )
            ... }
            >>> all_variants = BuildMatrix.generate_all_project_variants(projects)
            >>> len(all_variants["test"])
            2
        """
        all_variants = {}

        for project_name, config in projects.items():
            build_args = config.build_args or {}
            variants = BuildMatrix.generate_variants(project_name, build_args)
            all_variants[project_name] = variants

        return all_variants

    @staticmethod
    def get_total_variant_count(variants_dict: Dict[str, List[BuildVariant]]) -> int:
        """Count total number of variants across all projects.

        Args:
            variants_dict: Dictionary from generate_all_project_variants()

        Returns:
            Total number of container variants to build
        """
        return sum(len(variants) for variants in variants_dict.values())


def calculate_matrix_size(build_args: Dict[str, List[str]]) -> int:
    """Calculate the total number of combinations for given build arguments.

    Args:
        build_args: Dictionary mapping argument names to lists of values

    Returns:
        Number of combinations (product of list lengths)

    Example:
        >>> calculate_matrix_size({"branch": ["a", "b"], "mode": ["x", "y", "z"]})
        6
    """
    if not build_args:
        return 1

    size = 1
    for values in build_args.values():
        size *= len(values)
    return size
