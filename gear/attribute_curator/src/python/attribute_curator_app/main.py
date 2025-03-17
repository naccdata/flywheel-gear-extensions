"""Defines Attribute Curator."""

import logging
from enum import Enum
from typing import List

from curator.form_curator import FormCurator, UDSFormCurator
from curator.scheduling import ProjectCurationError, ProjectCurationScheduler
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_gear_toolkit.context.context import GearToolkitContext
from gear_execution.gear_execution import (
    GearExecutionError,
    InputFileWrapper,
)
from nacc_attribute_deriver.attribute_deriver import AttributeDeriver

log = logging.getLogger(__name__)


class CurationType(str, Enum):

    GENERAL = 'general'
    UDS = 'uds'


def run(context: GearToolkitContext, project: ProjectAdaptor,
        derive_rules: InputFileWrapper, date_key: str,
        acquisition_labels: List[str], curation_type: CurationType) -> None:
    """Runs the Attribute Curator process.

    Args:
        context: GearToolKitContext
        project: The project to be curated over
        deriver_rules: CSV file containing the derivation rules
        date_key: Date key to order data by
        acquisition_labels: Acquisition labels to filter by
        curation_type: Whether or not this is an UDS form
            TODO: this is kind of a hack, and mostly just done
            to distinguish when we need to grab an NP form for UDS
            - will require us to add to this list/factory for each
            distinguishable curation type though. better way to
            generalize?
    """
    deriver = AttributeDeriver(date_key=date_key, rules_file=derive_rules)

    if curation_type.value == CurationType.UDS:
        curator = UDSFormCurator(context=context, deriver=deriver)
    else:
        curator = FormCurator(context=context, deriver=deriver)

    try:
        scheduler = ProjectCurationScheduler.create(
            project=project,
            date_key=date_key,
            acquisition_labels=acquisition_labels)
    except ProjectCurationError as error:
        raise GearExecutionError(error) from error

    scheduler.apply(curator)
