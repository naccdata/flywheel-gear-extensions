"""Entry script for Form QC Coordinator."""

import json
import logging
from json.decoder import JSONDecodeError
from typing import Any, Optional

from flywheel.rest import ApiException
from flywheel_adaptor.subject_adaptor import SubjectAdaptor, ParticipantVisits
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (ClientWrapper, GearBotClient,
                                           GearEngine, GearExecutionError,
                                           GearExecutionEnvironment)
from inputs.parameter_store import ParameterStore
from inputs.yaml import YAMLReadError, load_from_stream
from pydantic import ValidationError

from form_qc_coordinator_app.coordinator import QCGearInfo
from form_qc_coordinator_app.main import run

log = logging.getLogger(__name__)


def validate_input_data(input_file_path: str,
                        subject_lbl: str) -> Optional[ParticipantVisits]:
    """Validates the input file.

    Args:
        input_file_path: Gear input file path
        subject_lbl: Flywheel subject label

    Returns:
        Optional[ParticipantVisits]: Info on set of visits to be validated
    """

    try:
        with open(input_file_path, 'r', encoding='utf-8 ') as input_file:
            input_data = load_from_stream(input_file)
    except (FileNotFoundError, YAMLReadError) as error:
        log.error('Failed to read the input file - %s', error)
        return None

    try:
        visits_info = ParticipantVisits.model_validate(input_data)
    except ValidationError as error:
        log.error('Input data not in expected format - %s', error)
        return None

    if visits_info and subject_lbl != visits_info.participant:
        log.error(
            'Partipant label in input file %s does not match with subject label %s',
            visits_info.participant, subject_lbl)
        return None

    return visits_info


def get_qc_gear_configs(configs_file_path: str, ) -> Optional[QCGearInfo]:
    """_summary_

    Args:
        config_file_path (str): _description_

    Returns:
        Dict[str, str]: _description_
    """
    try:
        with open(configs_file_path, mode='r', encoding='utf-8') as file_obj:
            config_data = json.load(file_obj)
    except (FileNotFoundError, JSONDecodeError, TypeError) as error:
        log.error('Failed to read the qc gear configs file - %s', error)
        return None

    try:
        gear_configs = QCGearInfo.model_validate(config_data)
    except ValidationError as error:
        log.error('QC gear config data not in expected format - %s', error)
        return None

    return gear_configs


class FormQCCoordinator(GearExecutionEnvironment):
    """The gear execution visitor for the form-qc-coordinator."""

    def __init__(self,
                 *,
                 client: ClientWrapper,
                 date_col: str,
                 check_all: bool = False):
        """
        Args:
            client: Flywheel SDK client wrapper
            date_col: variable name to sort the participant visits
            check_all: re-evaluate all visits for the module/participant
        """
        self._date_col = date_col
        self._check_all = check_all
        super().__init__(client=client)

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'FormQCCoordinator':
        """Creates a gear execution object, loads gear context.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """
        assert parameter_store, "Parameter store expected"
        client = GearBotClient.create(context=context,
                                      parameter_store=parameter_store)
        date_col = context.config.get('date_column', 'visitdate')
        check_all = context.config.get('check_all', False)

        return FormQCCoordinator(client=client,
                                 date_col=date_col,
                                 check_all=check_all)

    def run(self, context: GearToolkitContext) -> None:
        """Runs the form-qc-coordinator app.

        Args:
            context: the gear execution context
        """
        try:
            dest_container: Any = context.get_destination_container()
        except ApiException as error:
            raise GearExecutionError(
                f'Cannot find destination container: {error}') from error

        if dest_container.container_type != 'subject':
            raise GearExecutionError(
                'This gear must be executed at subject level - '
                'invalid gear destination type '
                f'{dest_container.container_type}')

        visits_file_path = context.get_input_path('visits_file')
        if not visits_file_path:
            raise GearExecutionError('visits_file not provided')

        visits_info = validate_input_data(visits_file_path,
                                          dest_container.label)
        if not visits_info:
            raise GearExecutionError(
                f'Error(s) in reading visit info file - {visits_file_path}')

        config_file_path = context.get_input_path('qc_configs_file')
        if not config_file_path:
            raise GearExecutionError('qc_configs_file not provided')

        qc_gear_info = get_qc_gear_configs(config_file_path)
        if not qc_gear_info:
            raise GearExecutionError(
                f'Error(s) in reading qc gear configs file - {config_file_path}'
            )

        run(gear_context=context,
            client_wrapper=self.client,
            subject=SubjectAdaptor(dest_container),
            date_col=self._date_col,
            visits_info=visits_info,
            qc_gear_info=qc_gear_info,
            check_all=self._check_all)


def main():
    """Main method for Form QC Coordinator."""

    GearEngine.create_with_parameter_store().run(gear_type=FormQCCoordinator)


if __name__ == "__main__":
    main()
