"""Entrypoint script for the identifer lookup app."""

import logging
import sys
from pathlib import Path
from typing import Dict, Optional

from centers.center_group import CenterError, CenterGroup
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (GearBotExecutionVisitor,
                                           GearExecutionEngine,
                                           GearExecutionError)
from identifer_app.main import run
from identifiers.database import create_session
from identifiers.identifiers_repository import IdentifierRepository
from identifiers.model import Identifier
from inputs.parameter_store import (ParameterError, ParameterStore,
                                    RDSParameters)
from outputs.errors import ListErrorWriter

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
log = logging.getLogger(__name__)


def get_identifiers(rds_parameters: RDSParameters,
                    adcid: int) -> Dict[str, Identifier]:
    """Gets all of the Identifier objects from the identifier database using
    the RDSParameters.

    Args:
      rds_parameters: the credentials for RDS MySQL with identifiers database
      adcid: the center ID
    Returns:
      the dictionary mapping from PTID to Identifier object
    """
    identifiers = {}
    identifers_session = create_session(rds_parameters)
    with identifers_session as session:
        identifiers_repo = IdentifierRepository(session)
        center_identifiers = identifiers_repo.list(adc_id=adcid)
        if center_identifiers:
            # pylint: disable=(not-an-iterable)
            identifiers = {
                identifier.ptid: identifier
                for identifier in center_identifiers
            }

    return identifiers


def get_adcid(proxy: FlywheelProxy, file_id: str) -> Optional[int]:
    """Get the adcid of the center group that owns the file.

    Args:
      proxy: the flwheel proxy object
      file_id: the ID for the file
    Returns:
      the ADCID for the center
    """
    file = proxy.get_file(file_id)
    group_id = file.parents.group
    groups = proxy.find_groups(group_id)
    center = CenterGroup.create_from_group(group=groups[0], proxy=proxy)
    return center.adcid


class IdentifierLookupVisitor(GearBotExecutionVisitor):
    """The gear execution visitor for the identifier lookup app."""

    def __init__(self):
        super().__init__()
        self.file_input = None
        self.rds_param_path = None
        self.rds_parameters = None

    def visit_context(self, context: GearToolkitContext):
        """Visits the context and gathers the input file and RDS parameters.

        Args:
            context: The gear context.
        """
        super().visit_context(context)
        self.rds_param_path = context.config.get('rds_parameter_path')
        if not self.rds_param_path:
            raise GearExecutionError(f'No value for rds_parameter_path')

        self.file_input = context.get_input('input_file')
        if not self.file_input:
            raise GearExecutionError('Missing input file')

    def visit_parameter_store(self, parameter_store: ParameterStore):
        """Visits the parameter store and loads the RDS parameters.

        Args:
            parameter_store: the parameter store object
        """
        super().visit_parameter_store(parameter_store)
        assert self.rds_param_path, 'RDS parameter path required'
        try:
            self.rds_parameters = parameter_store.get_rds_parameters(
                param_path=self.rds_param_path)
        except ParameterError as error:
            raise GearExecutionError(f'Parameter error: {error}') from error

    def __get_adcid(self, proxy: FlywheelProxy, file_id: str) -> int:
        """Gets the adcid for the center group that owns the file.

        Args:
            proxy: the flywheel proxy object
            file_id: the ID for the file
        Returns:
            the ADCID for the center
        """
        try:

            adcid = get_adcid(proxy=proxy, file_id=file_id)
        except CenterError as error:
            raise GearExecutionError(
                f'Unable to determine center ID for parent group of file: {error.message}'
            ) from error

        if not adcid:
            raise GearExecutionError('Unable to determine center ID for file')

        return adcid

    def run(self, gear: GearExecutionEngine):
        """Runs the identifier lookup app.

        Args:
            gear: the gear execution engine
        """
        assert self.client, 'Flywheel client required'
        assert self.file_input, 'Input file required'
        assert self.rds_parameters, 'RDS parameters required'
        assert gear.context, 'Gear context required'

        proxy = FlywheelProxy(client=self.client, dry_run=self.dry_run)

        file_id = self.file_input['object']['file_id']
        adcid = self.__get_adcid(proxy=proxy, file_id=file_id)

        identifiers = get_identifiers(rds_parameters=self.rds_parameters,
                                      adcid=adcid)
        if not identifiers:
            raise GearExecutionError('Unable to load center participant IDs')

        filename = f"{self.file_input['location']['name']}-identifier"
        input_path = Path(self.file_input['location']['path'])
        with open(input_path, mode='r', encoding='utf-8') as csv_file:
            with gear.context.open_output(f'{filename}.csv',
                                          mode='w',
                                          encoding='utf-8') as out_file:
                error_writer = ListErrorWriter(container_id=file_id)
                errors = run(input_file=csv_file,
                             identifiers=identifiers,
                             output_file=out_file,
                             error_writer=error_writer)
                gear.context.metadata.add_qc_result(
                    self.file_input,
                    name="validation",
                    state="FAIL" if errors else "PASS",
                    data={'data': error_writer.errors()})


def main():
    """The Identifiers Lookup gear reads a CSV file with rows for participants
    at a single ADRC, and having a PTID for the participant. The gear looks up
    the corresponding NACCID, and creates a new CSV file with the same
    contents, but with a new column for NACCID.

    Writes errors to a CSV file compatible with Flywheel error UI.
    """

    try:
        parameter_store = ParameterStore.create_from_environment()
    except ParameterError as error:
        log.error('Unable to create Parameter Store: %s', error)
        sys.exit(1)

    engine = GearExecutionEngine(parameter_store=parameter_store)

    try:
        engine.execute(IdentifierLookupVisitor())
    except GearExecutionError as error:
        log.error('Error: %s', error)
        sys.exit(1)

    if __name__ == "__main__":
        main()
