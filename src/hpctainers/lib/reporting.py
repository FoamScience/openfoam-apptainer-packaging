"""Report generation for container testing and analysis.

Generates JSON reports aggregating test results, security scans, and size analysis.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ContainerReport:
    """Aggregate report for a single container."""

    container_name: str
    container_path: Path
    build_date: Optional[datetime] = None
    test_results: Optional[Dict[str, Any]] = None
    security_scan: Optional[Dict[str, Any]] = None
    size_analysis: Optional[Dict[str, Any]] = None
    mpi_tests: Optional[Dict[str, Any]] = None


class ReportGenerator:
    """Generate aggregated reports."""

    def __init__(self, output_dir: Path = Path("reports")):
        """Initialize report generator.

        Args:
            output_dir: Directory for output reports
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_container_report(
        self,
        report: ContainerReport,
        output_name: Optional[str] = None
    ) -> Path:
        """Generate JSON report for a container.

        Args:
            report: Container report data
            output_name: Optional custom output name

        Returns:
            Path to generated report
        """
        if not output_name:
            output_name = f"{report.container_name}-report.json"

        output_path = self.output_dir / output_name

        report_dict = {
            "container_name": report.container_name,
            "container_path": str(report.container_path),
            "report_generated": datetime.now().isoformat(),
            "build_date": report.build_date.isoformat() if report.build_date else None
        }

        if report.test_results:
            report_dict["tests"] = report.test_results
        if report.security_scan:
            report_dict["security"] = report.security_scan
        if report.size_analysis:
            report_dict["size_analysis"] = report.size_analysis
        if report.mpi_tests:
            report_dict["mpi_tests"] = report.mpi_tests

        with open(output_path, 'w') as f:
            json.dump(report_dict, f, indent=2)

        logger.info(f"Generated report: {output_path}")
        return output_path

    def generate_summary_report(
        self,
        reports: List[ContainerReport],
        output_name: str = "summary-report.json"
    ) -> Path:
        """Generate summary report for multiple containers.

        Args:
            reports: List of container reports
            output_name: Output file name

        Returns:
            Path to generated report
        """
        output_path = self.output_dir / output_name

        summary = {
            "summary_generated": datetime.now().isoformat(),
            "total_containers": len(reports),
            "containers": []
        }

        total_tests = 0
        passed_tests = 0
        failed_tests = 0
        total_vulnerabilities = 0
        critical_vulns = 0

        for report in reports:
            container_summary = {
                "name": report.container_name,
                "path": str(report.container_path)
            }

            if report.test_results:
                test_count = len(report.test_results.get('results', []))
                passed = sum(1 for r in report.test_results.get('results', [])
                           if r.get('status') == 'passed')
                failed = test_count - passed

                container_summary["tests"] = {
                    "total": test_count,
                    "passed": passed,
                    "failed": failed
                }

                total_tests += test_count
                passed_tests += passed
                failed_tests += failed

            if report.security_scan:
                vulns = report.security_scan.get('total_vulnerabilities', 0)
                critical = report.security_scan.get('summary', {}).get('critical', 0)

                container_summary["security"] = {
                    "total_vulnerabilities": vulns,
                    "critical": critical
                }

                total_vulnerabilities += vulns
                critical_vulns += critical

            if report.size_analysis:
                container_summary["size_mb"] = report.size_analysis.get('size', {}).get('total_mb', 0)

            summary["containers"].append(container_summary)

        summary["aggregate_statistics"] = {
            "tests": {
                "total": total_tests,
                "passed": passed_tests,
                "failed": failed_tests,
                "pass_rate": (passed_tests / total_tests * 100) if total_tests > 0 else 0
            },
            "security": {
                "total_vulnerabilities": total_vulnerabilities,
                "critical_vulnerabilities": critical_vulns
            }
        }

        with open(output_path, 'w') as f:
            json.dump(summary, f, indent=2)

        logger.info(f"Generated summary report: {output_path}")
        return output_path

    def print_test_summary(self, test_results: Dict[str, Any]) -> None:
        """Print test results summary to console.

        Args:
            test_results: Test results dictionary
        """
        results = test_results.get('results', [])
        if not results:
            return

        passed = sum(1 for r in results if r.get('status') == 'passed')
        failed = sum(1 for r in results if r.get('status') == 'failed')
        errors = sum(1 for r in results if r.get('status') == 'error')

        logger.info("\n" + "=" * 60)
        logger.info("TEST SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total:  {len(results)}")
        logger.info(f"Passed: {passed}")
        logger.info(f"Failed: {failed}")
        logger.info(f"Errors: {errors}")

        if failed > 0 or errors > 0:
            logger.info("\nFailed/Error tests:")
            for result in results:
                if result.get('status') in ['failed', 'error']:
                    logger.info(f"  ✗ {result.get('test_name')}: {result.get('message')}")

    def print_security_summary(self, security_scan: Dict[str, Any]) -> None:
        """Print security scan summary to console.

        Args:
            security_scan: Security scan dictionary
        """
        summary = security_scan.get('summary', {})

        logger.info("\n" + "=" * 60)
        logger.info("SECURITY SCAN SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Scanner: {security_scan.get('scanner', 'unknown')}")
        logger.info(f"Status:  {security_scan.get('status', 'unknown')}")
        logger.info(f"\nVulnerabilities:")
        logger.info(f"  Critical: {summary.get('critical', 0)}")
        logger.info(f"  High:     {summary.get('high', 0)}")
        logger.info(f"  Medium:   {summary.get('medium', 0)}")
        logger.info(f"  Low:      {summary.get('low', 0)}")
        logger.info(f"\nTotal:      {security_scan.get('total_vulnerabilities', 0)}")

        if security_scan.get('error_message'):
            logger.warning(f"\nError: {security_scan['error_message']}")

    def print_size_summary(self, size_analysis: Dict[str, Any]) -> None:
        """Print size analysis summary to console.

        Args:
            size_analysis: Size analysis dictionary
        """
        size_info = size_analysis.get('size', {})

        logger.info("\n" + "=" * 60)
        logger.info("SIZE ANALYSIS SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total Size: {size_info.get('total_mb', 0):.2f} MB "
                   f"({size_info.get('total_gb', 0):.2f} GB)")

        components = size_analysis.get('component_breakdown', [])
        if components:
            logger.info(f"\nTop Components:")
            for comp in components[:5]:  # Top 5
                logger.info(f"  {comp['path']}: {comp['size_mb']:.2f} MB ({comp['percent']:.1f}%)")

        suggestions = size_analysis.get('optimization_suggestions', [])
        high_priority = [s for s in suggestions if s.get('priority') == 'high']

        if high_priority:
            logger.info(f"\nOptimization Opportunities ({len(high_priority)} high priority):")
            for sug in high_priority:
                savings = sug.get('potential_savings_mb', 0)
                logger.info(f"  • {sug['description']}")
                if savings > 0:
                    logger.info(f"    Potential savings: {savings:.1f} MB")
