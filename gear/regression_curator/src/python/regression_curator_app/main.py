"""Defines Regression Curator."""
import logging
from typing import Any, Dict

from curator.regression_curator import RegressionCurator
from curator.scheduling import ProjectCurationScheduler
from flywheel_gear_toolkit import GearToolkitContext

log = logging.getLogger(__name__)


def run(context: GearToolkitContext, baseline: Dict[str, Any],
        scheduler: ProjectCurationScheduler) -> None:
    """Runs the Attribute Curator process.

    Args:
        context: gear context
        baseline: Baseline attributes from QAF
        scheduler: Schedules the files to be curated
    """
    scheduler.apply(context=context, curator_type=RegressionCurator, baseline=baseline)
