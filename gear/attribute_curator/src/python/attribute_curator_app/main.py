"""Defines Attribute Curator."""

import logging
from typing import List

from curator.form_curator import FormCurator
from curator.scheduling import ProjectCurationError, ProjectCurationScheduler
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_gear_toolkit.context.context import GearToolkitContext
from gear_execution.gear_execution import GearExecutionError

from nacc_attribute_deriver.attribute_deriver import AttributeDeriver


log = logging.getLogger(__name__)


def run(context: GearToolkitContext,
        project: ProjectAdaptor,
        deriver_rules: InputFileWrapper,
        date_key: str,
        acquisition_labels: List[str]) -> None:
    """Runs the Attribute Curator process.

    Args:
        context: GearToolKitContext
        project: The project to be curated over
        deriver_rules: CSV file containing the derivation rules
        date_key: Date key to order data by
        acquisition_labels: Acquisition labels to filter by
    """
    deriver = AttributeDeriver(date_key=date_key,
                               rules_file=deriver_rules)

    # TODO: this might need to change per curation type, e.g. factory
    curator = FormCurator(context=context, deriver=deriver)

    try:
        scheduler = ProjectCurationScheduler.create(
            project=project, date_key=date_key)
    except ProjectCurationError as error:
        raise GearExecutionError(error) from error

    scheduler.apply(curator)
