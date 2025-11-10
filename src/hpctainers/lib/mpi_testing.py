"""MPI-specific testing for HPC containers.

Tests MPI functionality including hybrid mode (host + container MPI),
compatibility checks, and performance validation.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class MPIMode(Enum):
    """MPI execution modes."""
    HYBRID = "hybrid"  # Host MPI + container executable
    BIND = "bind"  # Bind-mounted MPI
    CONTAINERIZED = "containerized"  # Fully containerized MPI


@dataclass
class MPITestResult:
    """Result of an MPI test."""

    test_name: str
    mode: MPIMode
    ranks: int
    success: bool
    duration_s: float
    message: str = ""
    stdout: str = ""
    stderr: str = ""
    host_mpi_version: Optional[str] = None
    container_mpi_version: Optional[str] = None
    performance_metrics: Optional[dict] = None


class MPITester:
    """Execute MPI-specific tests on containers."""

    def __init__(self, container_path: Path):
        """Initialize MPI tester.

        Args:
            container_path: Path to .sif container file
        """
        self.container_path = Path(container_path)

        if not self.container_path.exists():
            raise FileNotFoundError(f"Container not found: {container_path}")

        self.host_mpi_version = self._detect_host_mpi()

    def _detect_host_mpi(self) -> Optional[str]:
        """Detect host MPI version.

        Returns:
            MPI version string or None if not found
        """
        try:
            result = subprocess.run(
                ['mpirun', '--version'],
                capture_output=True,
                text=True,
                check=False,
                timeout=5
            )

            if result.returncode == 0:
                version_match = re.search(r'(\d+\.\d+\.?\d*)', result.stdout)
                if version_match:
                    logger.info(f"Detected host MPI version: {version_match.group(1)}")
                    return version_match.group(1)

        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("Host MPI not detected")

        return None

    def _detect_container_mpi(self) -> Optional[str]:
        """Detect container MPI version.

        Returns:
            MPI version string or None if not found
        """
        try:
            result = subprocess.run(
                ['apptainer', 'exec', str(self.container_path), 'mpirun', '--version'],
                capture_output=True,
                text=True,
                check=False,
                timeout=5
            )

            if result.returncode == 0:
                version_match = re.search(r'(\d+\.\d+\.?\d*)', result.stdout)
                if version_match:
                    return version_match.group(1)

        except subprocess.TimeoutExpired:
            pass

        return None

    def test_hybrid_mpi(
        self,
        command: str,
        ranks: int = 2,
        timeout: int = 60
    ) -> MPITestResult:
        """Test hybrid MPI mode (host MPI + container executable).

        Args:
            command: Command to run inside container
            ranks: Number of MPI ranks
            timeout: Timeout in seconds

        Returns:
            Test result
        """
        import time

        if not self.host_mpi_version:
            return MPITestResult(
                test_name="hybrid_mpi",
                mode=MPIMode.HYBRID,
                ranks=ranks,
                success=False,
                duration_s=0,
                message="Host MPI not available"
            )

        start_time = time.time()

        try:
            cmd = [
                'mpirun',
                '-n', str(ranks),
                'apptainer', 'run',
                '--sharens',  # Share process namespace
                str(self.container_path),
                command
            ]

            logger.debug(f"Running: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout
            )

            duration = time.time() - start_time

            return MPITestResult(
                test_name="hybrid_mpi",
                mode=MPIMode.HYBRID,
                ranks=ranks,
                success=(result.returncode == 0),
                duration_s=duration,
                message="Hybrid MPI test passed" if result.returncode == 0 else f"Failed with exit code {result.returncode}",
                stdout=result.stdout,
                stderr=result.stderr,
                host_mpi_version=self.host_mpi_version
            )

        except subprocess.TimeoutExpired:
            return MPITestResult(
                test_name="hybrid_mpi",
                mode=MPIMode.HYBRID,
                ranks=ranks,
                success=False,
                duration_s=timeout,
                message=f"Test timed out after {timeout}s",
                host_mpi_version=self.host_mpi_version
            )

    def test_containerized_mpi(
        self,
        command: str,
        ranks: int = 2,
        timeout: int = 60
    ) -> MPITestResult:
        """Test fully containerized MPI (container MPI + container executable).

        Args:
            command: MPI command to run (e.g., 'mpirun -n 2 hostname')
            ranks: Number of MPI ranks
            timeout: Timeout in seconds

        Returns:
            Test result
        """
        import time

        container_mpi = self._detect_container_mpi()
        if not container_mpi:
            return MPITestResult(
                test_name="containerized_mpi",
                mode=MPIMode.CONTAINERIZED,
                ranks=ranks,
                success=False,
                duration_s=0,
                message="Container MPI not available"
            )

        start_time = time.time()

        try:
            cmd = [
                'apptainer', 'run',
                str(self.container_path),
                command
            ]

            logger.debug(f"Running: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout
            )

            duration = time.time() - start_time

            return MPITestResult(
                test_name="containerized_mpi",
                mode=MPIMode.CONTAINERIZED,
                ranks=ranks,
                success=(result.returncode == 0),
                duration_s=duration,
                message="Containerized MPI test passed" if result.returncode == 0 else f"Failed with exit code {result.returncode}",
                stdout=result.stdout,
                stderr=result.stderr,
                container_mpi_version=container_mpi
            )

        except subprocess.TimeoutExpired:
            return MPITestResult(
                test_name="containerized_mpi",
                mode=MPIMode.CONTAINERIZED,
                ranks=ranks,
                success=False,
                duration_s=timeout,
                message=f"Test timed out after {timeout}s",
                container_mpi_version=container_mpi
            )

    def test_mpi_compatibility(self) -> Tuple[bool, str]:
        """Test MPI compatibility between host and container.

        Returns:
            Tuple of (compatible, message)
        """
        host_version = self.host_mpi_version
        container_version = self._detect_container_mpi()

        if not host_version:
            return (False, "Host MPI not available")

        if not container_version:
            return (False, "Container MPI not available")

        try:
            host_parts = [int(x) for x in host_version.split('.')]
            container_parts = [int(x) for x in container_version.split('.')]

            host_major_minor = f"{host_parts[0]}.{host_parts[1]}"
            container_major_minor = f"{container_parts[0]}.{container_parts[1]}"

            if host_major_minor == container_major_minor:
                return (True, f"MPI versions compatible: host={host_version}, container={container_version}")
            else:
                return (False, f"MPI version mismatch: host={host_version}, container={container_version}")

        except (ValueError, IndexError):
            return (False, f"Failed to parse MPI versions: host={host_version}, container={container_version}")

    def test_basic_mpi_functionality(self, timeout: int = 60) -> MPITestResult:
        """Run basic MPI functionality test.

        Args:
            timeout: Timeout in seconds

        Returns:
            Test result
        """
        return self.test_hybrid_mpi('hostname', ranks=2, timeout=timeout)

    def run_comprehensive_mpi_tests(self) -> dict:
        """Run comprehensive MPI test suite.

        Returns:
            Dictionary of test results
        """
        results = {}

        logger.info("Running comprehensive MPI tests...")

        # Test 1: Host MPI compatibility check
        compatible, message = self.test_mpi_compatibility()
        results['compatibility'] = {
            'success': compatible,
            'message': message,
            'host_version': self.host_mpi_version,
            'container_version': self._detect_container_mpi()
        }
        logger.info(f"Compatibility check: {message}")

        # Test 2: Basic hybrid MPI
        logger.info("Testing hybrid MPI mode...")
        hybrid_result = self.test_basic_mpi_functionality()
        results['hybrid_mpi'] = {
            'success': hybrid_result.success,
            'message': hybrid_result.message,
            'duration_s': hybrid_result.duration_s
        }

        # Test 3: Containerized MPI
        logger.info("Testing containerized MPI mode...")
        containerized_result = self.test_containerized_mpi('mpirun -n 2 hostname')
        results['containerized_mpi'] = {
            'success': containerized_result.success,
            'message': containerized_result.message,
            'duration_s': containerized_result.duration_s
        }

        # Summary
        all_passed = all(r.get('success', False) for r in results.values())
        results['summary'] = {
            'all_tests_passed': all_passed,
            'total_tests': len(results) - 1,
            'passed': sum(1 for r in results.values() if r.get('success', False))
        }

        return results
