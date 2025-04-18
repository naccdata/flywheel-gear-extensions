"""Defines Regression Curator."""
import logging
from typing import Any, Dict

from curator.scheduling import ProjectCurationScheduler
from flywheel_gear_toolkit import GearToolkitContext
from outputs.errors import MPListErrorWriter

from .regression_curator import RegressionCurator

log = logging.getLogger(__name__)


def run(context: GearToolkitContext,
        baseline: Dict[str, Any],
        scheduler: ProjectCurationScheduler,
        error_writer: MPListErrorWriter) -> None:
    """Runs the Attribute Curator process.

    Args:
        context: gear context
        baseline: Baseline attributes from QAF
        scheduler: Schedules the files to be curated
        error_writer: Multi-processing error writer
    """
    scheduler.apply(context=context,
                    curator_type=RegressionCurator,
                    baseline=baseline,
                    error_writer=error_writer)
