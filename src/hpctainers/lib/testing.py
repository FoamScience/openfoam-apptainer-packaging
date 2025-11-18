"""Container testing framework.

Provides post-build validation for Apptainer containers including
command execution, file existence, version checks, and metadata validation.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TestType(Enum):
    """Types of tests supported."""
    COMMAND = "command"
    FILE_EXISTS = "file_exists"
    VERSION = "version"
    METADATA = "metadata"
    CONTENT = "content"


class TestSeverity(Enum):
    """Test severity levels."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class TestStatus(Enum):
    """Test execution status."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TestDefinition:
    """Definition of a single test."""
    name: str
    test_type: TestType
    severity: TestSeverity = TestSeverity.ERROR
    timeout: int = 60
    command: Optional[str] = None
    expect_success: bool = True
    expect_pattern: Optional[str] = None
    path: Optional[str] = None
    check_labels: Optional[List[str]] = None
    file_path: Optional[str] = None
    content_pattern: Optional[str] = None
    condition: Optional[str] = None


@dataclass
class TestResult:
    """Result of a test execution."""

    test_name: str
    test_type: TestType
    status: TestStatus
    duration_s: float
    severity: TestSeverity
    message: str = ""
    stdout: str = ""
    stderr: str = ""
    error: Optional[Exception] = None


class TestRunner:
    """Executes tests against Apptainer containers."""

    def __init__(self, container_path: Path, timeout: int = 300):
        """Initialize test runner.

        Args:
            container_path: Path to .sif container file
            timeout: Default timeout for tests in seconds
        """
        self.container_path = Path(container_path)
        self.default_timeout = timeout

        if not self.container_path.exists():
            raise FileNotFoundError(f"Container not found: {container_path}")

    def run_test(self, test_def: TestDefinition) -> TestResult:
        """Run a single test.

        Args:
            test_def: Test definition

        Returns:
            Test result
        """
        import time
        start_time = time.time()

        try:
            if test_def.test_type == TestType.COMMAND:
                result = self._run_command_test(test_def)
            elif test_def.test_type == TestType.FILE_EXISTS:
                result = self._run_file_exists_test(test_def)
            elif test_def.test_type == TestType.VERSION:
                result = self._run_version_test(test_def)
            elif test_def.test_type == TestType.METADATA:
                result = self._run_metadata_test(test_def)
            elif test_def.test_type == TestType.CONTENT:
                result = self._run_content_test(test_def)
            else:
                result = TestResult(
                    test_name=test_def.name,
                    test_type=test_def.test_type,
                    status=TestStatus.ERROR,
                    duration_s=0,
                    severity=test_def.severity,
                    message=f"Unknown test type: {test_def.test_type}"
                )
        except Exception as e:
            logger.exception(f"Test {test_def.name} raised exception")
            result = TestResult(
                test_name=test_def.name,
                test_type=test_def.test_type,
                status=TestStatus.ERROR,
                duration_s=time.time() - start_time,
                severity=test_def.severity,
                message=f"Exception: {e}",
                error=e
            )

        result.duration_s = time.time() - start_time
        return result

    def _run_command_test(self, test_def: TestDefinition) -> TestResult:
        """Execute command test."""
        if not test_def.command:
            return TestResult(
                test_name=test_def.name,
                test_type=TestType.COMMAND,
                status=TestStatus.ERROR,
                duration_s=0,
                severity=test_def.severity,
                message="No command specified"
            )

        try:
            result = subprocess.run(
                ['apptainer', 'exec', str(self.container_path), 'sh', '-c', test_def.command],
                capture_output=True,
                text=True,
                timeout=test_def.timeout,
                check=False
            )

            success = result.returncode == 0

            if test_def.expect_success and not success:
                return TestResult(
                    test_name=test_def.name,
                    test_type=TestType.COMMAND,
                    status=TestStatus.FAILED,
                    duration_s=0,
                    severity=test_def.severity,
                    message=f"Command failed (exit code {result.returncode})",
                    stdout=result.stdout,
                    stderr=result.stderr
                )

            if not test_def.expect_success and success:
                return TestResult(
                    test_name=test_def.name,
                    test_type=TestType.COMMAND,
                    status=TestStatus.FAILED,
                    duration_s=0,
                    severity=test_def.severity,
                    message="Command succeeded but failure was expected",
                    stdout=result.stdout,
                    stderr=result.stderr
                )

            if test_def.expect_pattern:
                combined_output = result.stdout + result.stderr
                if not re.search(test_def.expect_pattern, combined_output):
                    return TestResult(
                        test_name=test_def.name,
                        test_type=TestType.COMMAND,
                        status=TestStatus.FAILED,
                        duration_s=0,
                        severity=test_def.severity,
                        message=f"Output does not match pattern: {test_def.expect_pattern}",
                        stdout=result.stdout,
                        stderr=result.stderr
                    )

            return TestResult(
                test_name=test_def.name,
                test_type=TestType.COMMAND,
                status=TestStatus.PASSED,
                duration_s=0,
                severity=test_def.severity,
                message="Command executed successfully",
                stdout=result.stdout,
                stderr=result.stderr
            )

        except subprocess.TimeoutExpired:
            return TestResult(
                test_name=test_def.name,
                test_type=TestType.COMMAND,
                status=TestStatus.FAILED,
                duration_s=0,
                severity=test_def.severity,
                message=f"Command timed out after {test_def.timeout}s"
            )

    def _run_file_exists_test(self, test_def: TestDefinition) -> TestResult:
        """Check if file exists in container."""
        if not test_def.path:
            return TestResult(
                test_name=test_def.name,
                test_type=TestType.FILE_EXISTS,
                status=TestStatus.ERROR,
                duration_s=0,
                severity=test_def.severity,
                message="No path specified"
            )

        try:
            result = subprocess.run(
                ['apptainer', 'exec', str(self.container_path), 'test', '-e', test_def.path],
                capture_output=True,
                timeout=test_def.timeout,
                check=False
            )

            if result.returncode == 0:
                return TestResult(
                    test_name=test_def.name,
                    test_type=TestType.FILE_EXISTS,
                    status=TestStatus.PASSED,
                    duration_s=0,
                    severity=test_def.severity,
                    message=f"File exists: {test_def.path}"
                )
            else:
                return TestResult(
                    test_name=test_def.name,
                    test_type=TestType.FILE_EXISTS,
                    status=TestStatus.FAILED,
                    duration_s=0,
                    severity=test_def.severity,
                    message=f"File does not exist: {test_def.path}"
                )
        except subprocess.TimeoutExpired:
            return TestResult(
                test_name=test_def.name,
                test_type=TestType.FILE_EXISTS,
                status=TestStatus.FAILED,
                duration_s=0,
                severity=test_def.severity,
                message="Test timed out"
            )

    def _run_version_test(self, test_def: TestDefinition) -> TestResult:
        """Run version check test."""
        return self._run_command_test(test_def)

    def _run_metadata_test(self, test_def: TestDefinition) -> TestResult:
        """Check container metadata/labels."""
        if not test_def.check_labels:
            return TestResult(
                test_name=test_def.name,
                test_type=TestType.METADATA,
                status=TestStatus.ERROR,
                duration_s=0,
                severity=test_def.severity,
                message="No labels specified to check"
            )

        try:
            result = subprocess.run(
                ['apptainer', 'inspect', '--labels', str(self.container_path)],
                capture_output=True,
                text=True,
                timeout=test_def.timeout,
                check=True
            )

            labels_output = result.stdout
            missing_labels = []

            for label in test_def.check_labels:
                if label not in labels_output:
                    missing_labels.append(label)

            if missing_labels:
                return TestResult(
                    test_name=test_def.name,
                    test_type=TestType.METADATA,
                    status=TestStatus.FAILED,
                    duration_s=0,
                    severity=test_def.severity,
                    message=f"Missing labels: {', '.join(missing_labels)}",
                    stdout=labels_output
                )

            return TestResult(
                test_name=test_def.name,
                test_type=TestType.METADATA,
                status=TestStatus.PASSED,
                duration_s=0,
                severity=test_def.severity,
                message="All required labels present",
                stdout=labels_output
            )

        except subprocess.CalledProcessError as e:
            return TestResult(
                test_name=test_def.name,
                test_type=TestType.METADATA,
                status=TestStatus.FAILED,
                duration_s=0,
                severity=test_def.severity,
                message=f"Failed to inspect container: {e.stderr}",
                stderr=e.stderr if hasattr(e, 'stderr') else ""
            )

    def _run_content_test(self, test_def: TestDefinition) -> TestResult:
        """Check file content in container."""
        if not test_def.file_path or not test_def.content_pattern:
            return TestResult(
                test_name=test_def.name,
                test_type=TestType.CONTENT,
                status=TestStatus.ERROR,
                duration_s=0,
                severity=test_def.severity,
                message="file_path and content_pattern required"
            )

        try:
            result = subprocess.run(
                ['apptainer', 'exec', str(self.container_path), 'cat', test_def.file_path],
                capture_output=True,
                text=True,
                timeout=test_def.timeout,
                check=True
            )

            if re.search(test_def.content_pattern, result.stdout):
                return TestResult(
                    test_name=test_def.name,
                    test_type=TestType.CONTENT,
                    status=TestStatus.PASSED,
                    duration_s=0,
                    severity=test_def.severity,
                    message=f"Content matches pattern"
                )
            else:
                return TestResult(
                    test_name=test_def.name,
                    test_type=TestType.CONTENT,
                    status=TestStatus.FAILED,
                    duration_s=0,
                    severity=test_def.severity,
                    message=f"Content does not match pattern: {test_def.content_pattern}"
                )
        except subprocess.CalledProcessError:
            return TestResult(
                test_name=test_def.name,
                test_type=TestType.CONTENT,
                status=TestStatus.FAILED,
                duration_s=0,
                severity=test_def.severity,
                message=f"Failed to read file: {test_def.file_path}"
            )

    def run_all_tests(self, tests: List[TestDefinition], fail_fast: bool = False) -> List[TestResult]:
        """Run all tests.

        Args:
            tests: List of test definitions
            fail_fast: Stop on first failure

        Returns:
            List of test results
        """
        results = []

        for test in tests:
            logger.info(f"Running test: {test.name}")
            result = self.run_test(test)
            results.append(result)

            if result.status == TestStatus.PASSED:
                logger.info(f"✓ {test.name}: PASSED")
            elif result.status == TestStatus.FAILED:
                logger.warning(f"✗ {test.name}: FAILED - {result.message}")
                if fail_fast and result.severity == TestSeverity.ERROR:
                    logger.error("Stopping tests due to failure (fail_fast=True)")
                    break
            elif result.status == TestStatus.ERROR:
                logger.error(f"✗ {test.name}: ERROR - {result.message}")
                if fail_fast:
                    break

        return results


def parse_test_config(test_config: Dict[str, Any]) -> List[TestDefinition]:
    """Parse test configuration from YAML.

    Args:
        test_config: Test configuration dictionary

    Returns:
        List of test definitions
    """
    tests = []
    test_list = test_config.get('test_list', [])

    for test_dict in test_list:
        try:
            test_type = TestType(test_dict['type'])
            severity = TestSeverity(test_dict.get('severity', 'error'))

            test_def = TestDefinition(
                name=test_dict['name'],
                test_type=test_type,
                severity=severity,
                timeout=test_dict.get('timeout', 60),
                command=test_dict.get('command'),
                expect_success=test_dict.get('expect_success', True),
                expect_pattern=test_dict.get('expect_pattern'),
                path=test_dict.get('path'),
                check_labels=test_dict.get('check_labels'),
                file_path=test_dict.get('file_path'),
                content_pattern=test_dict.get('content_pattern'),
                condition=test_dict.get('condition')
            )

            tests.append(test_def)
        except Exception as e:
            logger.warning(f"Failed to parse test: {e}")
            continue

    return tests
