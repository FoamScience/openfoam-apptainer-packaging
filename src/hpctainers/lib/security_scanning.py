"""Container security scanning integration.

Integrates Trivy and Grype security scanners for Apptainer SIF containers.
Both tools support SIF format natively - no OCI conversion needed.
"""

from __future__ import annotations

import json
import logging
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Severity(Enum):
    """CVE severity levels."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class ScanStatus(Enum):
    """Scan execution status."""
    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"
    POLICY_VIOLATION = "policy_violation"


@dataclass
class Vulnerability:
    """Represents a security vulnerability."""

    cve_id: str
    severity: Severity
    package_name: str
    installed_version: str
    fixed_version: Optional[str] = None
    description: str = ""
    score: Optional[float] = None


@dataclass
class ScanResult:
    """Result of a security scan."""

    container_path: Path
    scanner: str
    scan_date: datetime
    status: ScanStatus
    vulnerabilities: List[Vulnerability] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)
    error_message: str = ""

    def get_severity_count(self, severity: Severity) -> int:
        """Get count of vulnerabilities by severity."""
        return self.summary.get(severity.value.lower(), 0)

    def has_critical(self) -> bool:
        """Check if scan found critical vulnerabilities."""
        return self.get_severity_count(Severity.CRITICAL) > 0

    def has_high(self) -> bool:
        """Check if scan found high severity vulnerabilities."""
        return self.get_severity_count(Severity.HIGH) > 0

    def total_vulnerabilities(self) -> int:
        """Get total number of vulnerabilities."""
        return len(self.vulnerabilities)


@dataclass
class ScanPolicy:
    """Security scan policy configuration."""

    fail_on_critical: bool = False
    fail_on_high: bool = False
    ignore_unfixed: bool = True
    max_critical: int = 0
    max_high: Optional[int] = None
    ignore_cves: List[str] = field(default_factory=list)

    def should_fail_build(self, scan_result: ScanResult) -> tuple[bool, str]:
        """Determine if build should fail based on scan results.

        Args:
            scan_result: Security scan result

        Returns:
            Tuple of (should_fail, reason)
        """
        if scan_result.status == ScanStatus.ERROR:
            return (False, "Scan failed - not failing build")

        critical_count = scan_result.get_severity_count(Severity.CRITICAL)
        high_count = scan_result.get_severity_count(Severity.HIGH)

        if self.fail_on_critical and critical_count > self.max_critical:
            return (True, f"{critical_count} critical vulnerabilities exceed threshold of {self.max_critical}")
        if self.fail_on_high and self.max_high is not None and high_count > self.max_high:
            return (True, f"{high_count} high vulnerabilities exceed threshold of {self.max_high}")

        return (False, "Scan passed policy checks")


class SecurityScanner(ABC):
    """Abstract base class for security scanners."""

    def __init__(self, policy: Optional[ScanPolicy] = None):
        """Initialize scanner.

        Args:
            policy: Scan policy configuration
        """
        self.policy = policy or ScanPolicy()

    @abstractmethod
    def scan(self, container_path: Path) -> ScanResult:
        """Scan container for vulnerabilities.

        Args:
            container_path: Path to container file

        Returns:
            Scan result
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if scanner is installed and available."""
        pass


class TrivyScanner(SecurityScanner):
    """Trivy security scanner integration.

    Trivy supports Apptainer SIF files natively:
    `trivy image container.sif`
    """

    def is_available(self) -> bool:
        """Check if Trivy is installed."""
        try:
            subprocess.run(
                ['trivy', '--version'],
                capture_output=True,
                check=True,
                timeout=5
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def scan(self, container_path: Path) -> ScanResult:
        """Scan container with Trivy.

        Args:
            container_path: Path to .sif file

        Returns:
            Scan result
        """
        if not container_path.exists():
            return ScanResult(
                container_path=container_path,
                scanner="trivy",
                scan_date=datetime.now(),
                status=ScanStatus.ERROR,
                error_message=f"Container not found: {container_path}"
            )

        try:
            cmd = ['trivy', 'image', '--format', 'json']

            if self.policy.ignore_unfixed:
                cmd.append('--ignore-unfixed')
            severities = []
            if self.policy.fail_on_critical:
                severities.append('CRITICAL')
            if self.policy.fail_on_high:
                severities.extend(['CRITICAL', 'HIGH'])

            if severities:
                cmd.extend(['--severity', ','.join(set(severities))])

            cmd.append(str(container_path))

            logger.debug(f"Running: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=300
            )

            if result.returncode != 0 and not result.stdout:
                return ScanResult(
                    container_path=container_path,
                    scanner="trivy",
                    scan_date=datetime.now(),
                    status=ScanStatus.ERROR,
                    error_message=f"Trivy scan failed: {result.stderr}"
                )

            try:
                scan_data = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                return ScanResult(
                    container_path=container_path,
                    scanner="trivy",
                    scan_date=datetime.now(),
                    status=ScanStatus.ERROR,
                    error_message=f"Failed to parse Trivy output: {e}"
                )

            vulnerabilities = []
            summary = {"critical": 0, "high": 0, "medium": 0, "low": 0}

            for result_item in scan_data.get('Results', []):
                for vuln in result_item.get('Vulnerabilities', []):
                    cve_id = vuln.get('VulnerabilityID', '')
                    if cve_id in self.policy.ignore_cves:
                        continue

                    severity_str = vuln.get('Severity', 'UNKNOWN').upper()
                    try:
                        severity = Severity[severity_str]
                    except KeyError:
                        severity = Severity.UNKNOWN

                    vulnerability = Vulnerability(
                        cve_id=cve_id,
                        severity=severity,
                        package_name=vuln.get('PkgName', 'unknown'),
                        installed_version=vuln.get('InstalledVersion', 'unknown'),
                        fixed_version=vuln.get('FixedVersion'),
                        description=vuln.get('Description', '')[:200],  # Truncate
                        score=vuln.get('CVSS', {}).get('nvd', {}).get('V3Score')
                    )

                    vulnerabilities.append(vulnerability)

                    if severity != Severity.UNKNOWN:
                        summary[severity.value.lower()] += 1

            scan_result = ScanResult(
                container_path=container_path,
                scanner="trivy",
                scan_date=datetime.now(),
                status=ScanStatus.SUCCESS,
                vulnerabilities=vulnerabilities,
                summary=summary
            )

            should_fail, reason = self.policy.should_fail_build(scan_result)
            if should_fail:
                scan_result.status = ScanStatus.POLICY_VIOLATION
                scan_result.error_message = reason

            return scan_result

        except subprocess.TimeoutExpired:
            return ScanResult(
                container_path=container_path,
                scanner="trivy",
                scan_date=datetime.now(),
                status=ScanStatus.ERROR,
                error_message="Trivy scan timed out after 300s"
            )
        except Exception as e:
            logger.exception("Unexpected error during Trivy scan")
            return ScanResult(
                container_path=container_path,
                scanner="trivy",
                scan_date=datetime.now(),
                status=ScanStatus.ERROR,
                error_message=f"Unexpected error: {e}"
            )


class GrypeScanner(SecurityScanner):
    """Grype security scanner integration.

    Grype supports Apptainer SIF files natively:
    `grype singularity:container.sif`
    """

    def is_available(self) -> bool:
        """Check if Grype is installed."""
        try:
            subprocess.run(
                ['grype', 'version'],
                capture_output=True,
                check=True,
                timeout=5
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def scan(self, container_path: Path) -> ScanResult:
        """Scan container with Grype.

        Args:
            container_path: Path to .sif file

        Returns:
            Scan result
        """
        if not container_path.exists():
            return ScanResult(
                container_path=container_path,
                scanner="grype",
                scan_date=datetime.now(),
                status=ScanStatus.ERROR,
                error_message=f"Container not found: {container_path}"
            )

        try:
            cmd = ['grype', f'singularity:{container_path}', '-o', 'json']

            logger.debug(f"Running: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=300
            )

            if result.returncode != 0 and not result.stdout:
                return ScanResult(
                    container_path=container_path,
                    scanner="grype",
                    scan_date=datetime.now(),
                    status=ScanStatus.ERROR,
                    error_message=f"Grype scan failed: {result.stderr}"
                )

            try:
                scan_data = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                return ScanResult(
                    container_path=container_path,
                    scanner="grype",
                    scan_date=datetime.now(),
                    status=ScanStatus.ERROR,
                    error_message=f"Failed to parse Grype output: {e}"
                )

            vulnerabilities = []
            summary = {"critical": 0, "high": 0, "medium": 0, "low": 0}

            for match in scan_data.get('matches', []):
                vuln_data = match.get('vulnerability', {})
                cve_id = vuln_data.get('id', '')

                if cve_id in self.policy.ignore_cves:
                    continue

                severity_str = vuln_data.get('severity', 'Unknown').upper()
                try:
                    severity = Severity[severity_str]
                except KeyError:
                    severity = Severity.UNKNOWN

                fixed_version = vuln_data.get('fix', {}).get('versions', [])
                if self.policy.ignore_unfixed and not fixed_version:
                    continue

                artifact = match.get('artifact', {})
                vulnerability = Vulnerability(
                    cve_id=cve_id,
                    severity=severity,
                    package_name=artifact.get('name', 'unknown'),
                    installed_version=artifact.get('version', 'unknown'),
                    fixed_version=fixed_version[0] if fixed_version else None,
                    description=vuln_data.get('description', '')[:200]
                )

                vulnerabilities.append(vulnerability)

                if severity != Severity.UNKNOWN:
                    summary[severity.value.lower()] += 1

            scan_result = ScanResult(
                container_path=container_path,
                scanner="grype",
                scan_date=datetime.now(),
                status=ScanStatus.SUCCESS,
                vulnerabilities=vulnerabilities,
                summary=summary
            )

            should_fail, reason = self.policy.should_fail_build(scan_result)
            if should_fail:
                scan_result.status = ScanStatus.POLICY_VIOLATION
                scan_result.error_message = reason

            return scan_result

        except subprocess.TimeoutExpired:
            return ScanResult(
                container_path=container_path,
                scanner="grype",
                scan_date=datetime.now(),
                status=ScanStatus.ERROR,
                error_message="Grype scan timed out after 300s"
            )
        except Exception as e:
            logger.exception("Unexpected error during Grype scan")
            return ScanResult(
                container_path=container_path,
                scanner="grype",
                scan_date=datetime.now(),
                status=ScanStatus.ERROR,
                error_message=f"Unexpected error: {e}"
            )


def create_scanner(scanner_type: str, policy: Optional[ScanPolicy] = None) -> SecurityScanner:
    """Factory function to create scanner instance.

    Args:
        scanner_type: Scanner type ('trivy' or 'grype')
        policy: Scan policy configuration

    Returns:
        Scanner instance

    Raises:
        ValueError: If scanner type is unknown
    """
    scanner_type = scanner_type.lower()

    if scanner_type == 'trivy':
        return TrivyScanner(policy)
    elif scanner_type == 'grype':
        return GrypeScanner(policy)
    else:
        raise ValueError(f"Unknown scanner type: {scanner_type}. Use 'trivy' or 'grype'.")


def save_scan_report(scan_result: ScanResult, output_path: Path) -> None:
    """Save scan result to JSON file.

    Args:
        scan_result: Scan result to save
        output_path: Path to output file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "container": str(scan_result.container_path),
        "scanner": scan_result.scanner,
        "scan_date": scan_result.scan_date.isoformat(),
        "status": scan_result.status.value,
        "summary": scan_result.summary,
        "total_vulnerabilities": scan_result.total_vulnerabilities(),
        "error_message": scan_result.error_message,
        "vulnerabilities": [
            {
                "cve_id": v.cve_id,
                "severity": v.severity.value,
                "package": v.package_name,
                "installed_version": v.installed_version,
                "fixed_version": v.fixed_version,
                "description": v.description,
                "score": v.score
            }
            for v in scan_result.vulnerabilities
        ]
    }

    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)

    logger.info(f"Saved security scan report to {output_path}")
