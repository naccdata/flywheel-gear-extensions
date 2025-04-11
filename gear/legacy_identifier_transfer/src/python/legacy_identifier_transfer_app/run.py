"""Entry script for legacy_identifier_transfer."""

import logging
from typing import Any, Dict, Optional, Tuple

from datastore.forms_store import FormsStore
from enrollment.enrollment_project import EnrollmentProject
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor, ProjectError
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from identifiers.identifiers_lambda_repository import (
    IdentifiersLambdaRepository,
    IdentifiersMode,
)
from identifiers.identifiers_repository import (
    IdentifierRepository,
    IdentifierRepositoryError,
)
from identifiers.model import IdentifierObject
from inputs.parameter_store import ParameterStore
from keys.keys import DefaultValues
from lambdas.lambda_function import LambdaClient, create_lambda_client

from legacy_identifier_transfer_app.main import run

log = logging.getLogger(__name__)


def get_identifiers(identifiers_repo: IdentifierRepository,
                    adcid: int) -> Dict[str, IdentifierObject]:
    """Gets all of the Identifier objects from the identifier database using
    the RDSParameters.

    Args:
      rds_parameters: the credentials for RDS MySQL with identifiers database
      adcid: the center ID
    Returns:
      the dictionary mapping from NACCID to Identifier object
    """
    identifiers = {}
    center_identifiers = identifiers_repo.list(adcid=adcid)
    if center_identifiers:
        # pylint: disable=(not-an-iterable)
        identifiers = {
            identifier.naccid: identifier
            for identifier in center_identifiers
        }
    log.info(f"Found {len(identifiers)} identifiers for center {adcid}")
    return identifiers


# This is adapted from redcap_fw_transfer gear
def get_destination_group_and_project(dest_container: Any) -> Tuple[str, str]:
    """Find the flywheel group id and project id for the destination project.

    Args:
        dest_container: Flywheel container in which the gear is triggered

    Returns:
        Tuple[str, str]: group id, project id

    Raises:
        GearExecutionError if any error occurred while retrieving parent info
    """

    if not dest_container:
        raise GearExecutionError('Gear destination not set')

    if dest_container.container_type == 'project':
        project_id = dest_container.id
        group_id = dest_container.group
    elif dest_container.container_type in ('subject', 'session',
                                           'acquisition'):
        project_id = dest_container.parents.project
        group_id = dest_container.parents.group
    else:
        raise GearExecutionError(
            f'Invalid gear destination type {dest_container.container_type}')

    return group_id, project_id


class LegacyIdentifierTransferVisitor(GearExecutionEnvironment):
    """The gear execution visitor for the Legacy identifier transfer gear."""

    def __init__(self, admin_id: str, client: ClientWrapper,
                 identifiers_mode: IdentifiersMode, legacy_ingest_label: str):
        super().__init__(client=client)
        self.__admin_id = admin_id
        self.__identifiers_mode: IdentifiersMode = identifiers_mode
        self.__legacy_ingest_label = legacy_ingest_label
        self.__dry_run = client.dry_run

    @classmethod
    def create(
        cls, context: GearToolkitContext,
        parameter_store: Optional[ParameterStore]
    ) -> 'LegacyIdentifierTransferVisitor':
        """Creates a legacy naccid transfer execution visitor.

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

        admin_id = context.config.get("admin_group",
                                      DefaultValues.NACC_GROUP_ID)
        mode = context.config.get("identifiers_mode", "prod")
        legacy_ingest_label = context.config.get(
            "legacy_ingest_label", DefaultValues.LEGACY_PRJ_LABEL)

        return LegacyIdentifierTransferVisitor(
            admin_id=admin_id,
            client=client,
            identifiers_mode=mode,
            legacy_ingest_label=legacy_ingest_label)

    def __get_adcid(self, group_id: str) -> Optional[int]:
        """Get ADCID for the specified center.

        Args:
            group_id: Flywheel Group ID

        Raises:
            GearExecutionError: if admin group not found

        Returns:
            Optional[int]: ADCID for the center or None
        """
        try:
            admin_group = self.admin_group(admin_id=self.__admin_id)
            if not admin_group:
                raise GearExecutionError("No admin group found")
            return admin_group.get_adcid(group_id)
        except ApiException as error:
            log.error(f"Error getting ADCID: {error}")
            return None

    def run(self, context: GearToolkitContext) -> None:
        """Runs the legacy NACCID transfer gear.

        Args: context: The gear execution context
        """

        assert context, "Gear context expected"

        # Get destination container
        try:
            dest_container = context.get_destination_container()
        except ApiException as error:
            raise GearExecutionError(
                f"Error getting destination container: {error}") from error

        if not dest_container:
            raise GearExecutionError("No destination container found")

        log.info(
            f"Destination container: {dest_container.label}")  # type: ignore

        # Get Group and Project IDs, ADCID for group
        group_id, project_id = get_destination_group_and_project(
            dest_container)
        log.info(f"group_id: {group_id}")

        adcid = self.__get_adcid(group_id)
        if adcid is None:
            raise GearExecutionError(
                f'Unable to determine ADCID for group {group_id}')

        log.info(f"ADCID: {adcid}")

        # Get all identifiers for given adcid
        try:
            identifiers = get_identifiers(
                identifiers_repo=IdentifiersLambdaRepository(
                    client=LambdaClient(client=create_lambda_client()),
                    mode=self.__identifiers_mode),
                adcid=adcid)
        except IdentifierRepositoryError as error:
            raise GearExecutionError(error) from error

        if not identifiers:
            raise GearExecutionError(
                f'Unable to load identifiers for center {group_id} - ADCID {adcid}'
            )

        # Initialize enrollment project adapter
        group = self.proxy.find_group(group_id=group_id)
        if not group:
            raise GearExecutionError(f'Unable to get center group: {group_id}')
        log.info(f"Group: {group.label}")

        project = group.get_project_by_id(project_id)
        if not project:
            raise GearExecutionError(
                f'Unable to get parent project: {project_id}')
        log.info(f"Project: {project.label}")
        enrollment_project = EnrollmentProject.create_from(project)
        log.info(f"Enrollment project: {enrollment_project.label}")

        try:
            legacy_project = ProjectAdaptor.create(
                proxy=self.proxy,
                group_id=group_id,
                project_label=self.__legacy_ingest_label)
        except ProjectError as error:
            raise GearExecutionError(
                f"Could not find {group_id}/{self.__legacy_ingest_label}: {error}"
            ) from error

        forms_store = FormsStore(ingest_project=project,
                                 legacy_project=legacy_project)

        sender_email = context.config.get('sender_email', 'nacchelp@uw.edu')
        target_emails = context.config.get('target_emails', 'nacc_dev@uw.edu')
        target_emails = [x.strip() for x in target_emails.split(',')]

        run(identifiers=identifiers,
            enrollment_project=enrollment_project,
            forms_store=forms_store,
            sender_email=sender_email,
            target_emails=target_emails,
            dry_run=self.__dry_run)


def main():
    """The Legacy NACCID transfer gear looks up all of the NACCIDs for a
    center.

    If the center does not already have a Subject with a given NACCID,
    it creates a new subject at that center for that participant.
    """

    GearEngine().create_with_parameter_store().run(
        gear_type=LegacyIdentifierTransferVisitor)


if __name__ == "__main__":
    main()
