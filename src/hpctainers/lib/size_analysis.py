"""Container size analysis and optimization.

Analyzes Apptainer SIF file sizes and provides optimization recommendations.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class SIFObject:
    """Represents an object in SIF file structure."""

    id: int
    group: str
    link: str
    size_bytes: int
    object_type: str

    @property
    def size_mb(self) -> float:
        """Get size in megabytes."""
        return self.size_bytes / (1024 * 1024)


@dataclass
class ComponentSize:
    """Size of a component within container."""

    path: str
    size_bytes: int
    percent: float

    @property
    def size_mb(self) -> float:
        """Get size in megabytes."""
        return self.size_bytes / (1024 * 1024)


@dataclass
class OptimizationSuggestion:
    """Optimization recommendation."""

    category: str
    description: str
    potential_savings_mb: float
    priority: str  # high, medium, low
    implementation: str


@dataclass
class SizeAnalysisResult:
    """Result of size analysis."""

    container_path: Path
    total_bytes: int
    sif_objects: List[SIFObject] = field(default_factory=list)
    component_breakdown: List[ComponentSize] = field(default_factory=list)
    package_count: int = 0
    optimization_suggestions: List[OptimizationSuggestion] = field(default_factory=list)

    @property
    def total_mb(self) -> float:
        """Get total size in megabytes."""
        return self.total_bytes / (1024 * 1024)

    @property
    def total_gb(self) -> float:
        """Get total size in gigabytes."""
        return self.total_bytes / (1024 * 1024 * 1024)


class SizeAnalyzer:
    """Analyzes container sizes and provides optimization suggestions."""

    def __init__(self, container_path: Path):
        """Initialize size analyzer.

        Args:
            container_path: Path to .sif container file
        """
        self.container_path = Path(container_path)

        if not self.container_path.exists():
            raise FileNotFoundError(f"Container not found: {container_path}")

    def analyze(self) -> SizeAnalysisResult:
        """Perform complete size analysis.

        Returns:
            Size analysis result
        """
        result = SizeAnalysisResult(
            container_path=self.container_path,
            total_bytes=self.container_path.stat().st_size
        )

        result.sif_objects = self._analyze_sif_structure()
        result.component_breakdown = self._analyze_components()
        result.package_count = self._count_packages()
        result.optimization_suggestions = self._generate_suggestions(result)

        return result

    def _analyze_sif_structure(self) -> List[SIFObject]:
        """Parse SIF file structure using apptainer sif list.

        Returns:
            List of SIF objects
        """
        try:
            result = subprocess.run(
                ['apptainer', 'sif', 'list', str(self.container_path)],
                capture_output=True,
                text=True,
                check=True,
                timeout=30
            )

            objects = []
            for line in result.stdout.strip().split('\n')[1:]:
                parts = line.split()
                if len(parts) >= 5:
                    try:
                        obj = SIFObject(
                            id=int(parts[0].strip('|')),
                            group=parts[1].strip('|'),
                            link=parts[2].strip('|'),
                            size_bytes=int(parts[3].strip('|')),
                            object_type=parts[4].strip('|')
                        )
                        objects.append(obj)
                    except (ValueError, IndexError):
                        continue

            return objects

        except subprocess.CalledProcessError:
            logger.warning("Failed to analyze SIF structure")
            return []
        except subprocess.TimeoutExpired:
            logger.warning("SIF analysis timed out")
            return []

    def _analyze_components(self) -> List[ComponentSize]:
        """Analyze size of major components inside container.

        Note: Sizes are uncompressed sizes within the container filesystem,
        which may exceed the compressed .sif file size.

        Returns:
            List of component sizes
        """
        paths_to_check = ['/opt', '/usr', '/var']
        raw_components = []
        for path in paths_to_check:
            size_bytes = self._get_directory_size(path)
            if size_bytes > 0:
                raw_components.append((path, size_bytes))
        total_measured = sum(size for _, size in raw_components)
        if total_measured == 0:
            return []
        components = []
        for path, size_bytes in raw_components:
            percent = (size_bytes / total_measured) * 100 if total_measured > 0 else 0
            components.append(ComponentSize(
                path=path,
                size_bytes=size_bytes,
                percent=percent
            ))
        components.sort(key=lambda x: x.size_bytes, reverse=True)

        return components

    def _get_directory_size(self, path: str) -> int:
        """Get size of directory inside container.

        Args:
            path: Path to directory

        Returns:
            Size in bytes (0 if error)
        """
        try:
            result = subprocess.run(
                ['apptainer', 'exec', '--contain', '--no-home',
                 str(self.container_path), 'sh', '-c',
                 f'du -sb {path} 2>/dev/null | cut -f1'],
                capture_output=True,
                text=True,
                check=False,
                timeout=60
            )

            if result.returncode == 0 and result.stdout.strip():
                size = int(result.stdout.strip())
                container_size = self.container_path.stat().st_size
                if size > container_size * 3:
                    logger.warning(f"Directory {path} size ({size}) seems unrealistic, skipping")
                    return 0
                return size

        except (subprocess.TimeoutExpired, ValueError) as e:
            logger.debug(f"Failed to get size for {path}: {e}")
            pass

        return 0

    def _count_packages(self) -> int:
        """Count installed packages in container.

        Returns:
            Package count (0 if unable to determine)
        """
        # Try dpkg for Debian/Ubuntu
        try:
            result = subprocess.run(
                ['apptainer', 'exec', '--contain', '--no-home',
                 str(self.container_path), 'sh', '-c',
                 'dpkg -l 2>/dev/null | grep -c "^ii"'],
                capture_output=True,
                text=True,
                check=False,
                timeout=30
            )

            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip())

        except (subprocess.TimeoutExpired, ValueError):
            pass

        # Try rpm for RHEL/CentOS
        try:
            result = subprocess.run(
                ['apptainer', 'exec', '--contain', '--no-home',
                 str(self.container_path), 'sh', '-c',
                 'rpm -qa 2>/dev/null | wc -l'],
                capture_output=True,
                text=True,
                check=False,
                timeout=30
            )

            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip())

        except (subprocess.TimeoutExpired, ValueError):
            pass

        return 0

    def _generate_suggestions(self, analysis: SizeAnalysisResult) -> List[OptimizationSuggestion]:
        """Generate optimization suggestions based on analysis.

        Args:
            analysis: Size analysis result

        Returns:
            List of optimization suggestions
        """
        suggestions = []

        cache_size = self._check_cache_files()
        if cache_size > 10 * 1024 * 1024:  # > 10MB
            suggestions.append(OptimizationSuggestion(
                category="cache_cleanup",
                description=f"APT cache contains {cache_size / (1024*1024):.1f}MB of cached files",
                potential_savings_mb=cache_size / (1024 * 1024),
                priority="high",
                implementation="Add to %post section:\napt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*"
            ))

        doc_size = self._check_documentation()
        if doc_size > 5 * 1024 * 1024:  # > 5MB
            suggestions.append(OptimizationSuggestion(
                category="documentation",
                description=f"Documentation files ({doc_size / (1024*1024):.1f}MB) can be removed",
                potential_savings_mb=doc_size / (1024 * 1024),
                priority="medium",
                implementation="Add to %post section:\nrm -rf /usr/share/doc/* /usr/share/man/* /usr/share/info/*"
            ))

        if self._has_build_tools():
            container_size_mb = self.analysis.size.total_mb
            estimated_build_tools_mb = min(
                container_size_mb * 0.15,  # 15% of container size
                200.0
            )
            estimated_build_tools_mb = round(estimated_build_tools_mb, 1)

            suggestions.append(OptimizationSuggestion(
                category="build_tools",
                description="Build tools (gcc, g++, make) are present - consider multi-stage build",
                potential_savings_mb=estimated_build_tools_mb,
                priority="high",
                implementation="Use multi-stage build:\n"
                               "Stage 1: Build with gcc/g++\n"
                               "Stage 2: Copy binaries, install only runtime deps"
            ))

        if not suggestions:
            suggestions.append(OptimizationSuggestion(
                category="general",
                description="Container appears well-optimized",
                potential_savings_mb=0.0,
                priority="info",
                implementation="No specific optimizations recommended at this time"
            ))
        else:
            suggestions.append(OptimizationSuggestion(
                category="best_practices",
                description="Combine apt operations in single layer",
                potential_savings_mb=0.0,
                priority="low",
                implementation="Combine:\napt-get update && apt-get install ... && apt-get clean"
            ))

        return suggestions

    def _check_cache_files(self) -> int:
        """Check size of cache directories.

        Returns:
            Total cache size in bytes
        """
        try:
            result = subprocess.run(
                ['apptainer', 'exec', '--contain', '--no-home',
                 str(self.container_path), 'sh', '-c',
                 'du -sb /var/cache 2>/dev/null | cut -f1'],
                capture_output=True,
                text=True,
                check=False,
                timeout=30
            )

            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip())

        except (subprocess.TimeoutExpired, ValueError):
            pass

        return 0

    def _check_documentation(self) -> int:
        """Check size of documentation files.

        Returns:
            Total doc size in bytes
        """
        doc_paths = ['/usr/share/doc', '/usr/share/man', '/usr/share/info']
        total = 0

        for path in doc_paths:
            size = self._get_directory_size(path)
            total += size

        return total

    def _has_build_tools(self) -> bool:
        """Check if build tools are present.

        Returns:
            True if build tools found
        """
        tools = ['gcc', 'g++', 'make']

        for tool in tools:
            try:
                result = subprocess.run(
                    ['apptainer', 'exec', str(self.container_path), 'which', tool],
                    capture_output=True,
                    check=False,
                    timeout=10
                )

                if result.returncode == 0:
                    return True

            except subprocess.TimeoutExpired:
                pass

        return False


def save_analysis_report(analysis: SizeAnalysisResult, output_path: Path) -> None:
    """Save size analysis report to JSON file.

    Args:
        analysis: Size analysis result
        output_path: Path to output file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "container": str(analysis.container_path),
        "size": {
            "total_bytes": analysis.total_bytes,
            "total_mb": analysis.total_mb,
            "total_gb": analysis.total_gb
        },
        "sif_structure": [
            {
                "id": obj.id,
                "group": obj.group,
                "type": obj.object_type,
                "size_mb": obj.size_mb
            }
            for obj in analysis.sif_objects
        ],
        "component_breakdown": [
            {
                "path": comp.path,
                "size_mb": comp.size_mb,
                "percent": comp.percent
            }
            for comp in analysis.component_breakdown
        ],
        "package_count": analysis.package_count,
        "optimization_suggestions": [
            {
                "category": sug.category,
                "description": sug.description,
                "potential_savings_mb": sug.potential_savings_mb,
                "priority": sug.priority,
                "implementation": sug.implementation
            }
            for sug in analysis.optimization_suggestions
        ]
    }

    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)

    logger.info(f"Saved size analysis report to {output_path}")
