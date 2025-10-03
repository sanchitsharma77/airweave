"""Core test runner that orchestrates the entire testing process."""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from monke.core.config import TestConfig
from monke.core.flow import TestFlow
from monke.utils.logging import get_logger


@dataclass
class TestResult:
    """Result of a test execution."""

    success: bool
    duration: float
    metrics: Dict[str, Any]
    errors: List[str]
    warnings: List[str]


def compute_test_duration(metrics: Dict[str, Any]) -> float:
    """Compute total test duration from metrics.

    Prefers wall-clock time if available, otherwise sums step durations.
    """
    # Prefer wall clock time if available
    wall_time = metrics.get("total_duration_wall_clock")
    if isinstance(wall_time, (int, float)):
        return float(wall_time)

    # Otherwise sum step durations
    total = 0.0
    for key, value in metrics.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if key.endswith("_duration"):
                total += float(value)
    return total


class TestRunner:
    """Orchestrates test execution using TestFlow."""

    def __init__(self, config_path: str, run_id: Optional[str] = None):
        """Initialize the test runner.

        Args:
            config_path: Path to the test configuration file
            run_id: Optional run ID for tracking
        """
        self.config = TestConfig.from_file(config_path)
        self.logger = get_logger("test_runner")
        self.run_id = run_id

    async def run_tests(self) -> List[TestResult]:
        """Run all configured tests."""
        self.logger.info(f"🚀 Starting test run: {self.config.name}")
        self.logger.info(f"📝 Description: {self.config.description}")
        self.logger.info(f"🔗 Connector: {self.config.connector.type}")

        try:
            # Create test flow
            test_flow = TestFlow.create(self.config, run_id=self.run_id)

            # Setup environment
            if not await test_flow.setup():
                raise Exception("Failed to setup test environment")

            # Execute test flow
            await test_flow.execute()

            # Cleanup
            await test_flow.cleanup()

            # Build and return result
            metrics = test_flow.get_metrics()
            duration = compute_test_duration(metrics)

            result = TestResult(
                success=True,
                duration=duration,
                metrics=metrics,
                errors=[],
                warnings=test_flow.get_warnings(),
            )
            return [result]

        except Exception as e:
            self.logger.error(f"❌ Test failed: {e}")
            # Try to get partial metrics if available
            metrics = {}
            warnings = []
            if "test_flow" in locals():
                metrics = test_flow.get_metrics()
                warnings = test_flow.get_warnings()

            return [
                TestResult(
                    success=False,
                    duration=compute_test_duration(metrics),
                    metrics=metrics,
                    errors=[str(e)],
                    warnings=warnings,
                )
            ]
