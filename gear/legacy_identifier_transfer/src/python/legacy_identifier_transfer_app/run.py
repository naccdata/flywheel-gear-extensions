"""Entry script for legacy_identifier_transfer."""

import logging
from typing import Any, Dict, Optional, Tuple

from datastore.forms_store import FormsStore
from enrollment.enrollment_project import EnrollmentProject
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor, ProjectError
from fw_gear import GearContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from identifiers.identifiers_lambda_repository import (
    IdentifiersLambdaRepository,
)
from identifiers.identifiers_repository import (
    IdentifierRepository,
    IdentifierRepositoryError,
)
from identifiers.model import IdentifierObject, IdentifiersMode
from inputs.parameter_store import ParameterStore
from keys.keys import DefaultValues
from lambdas.lambda_function import LambdaClient, create_lambda_client

from legacy_identifier_transfer_app.main import run

log = logging.getLogger(__name__)


def get_identifiers(
    identifiers_repo: IdentifierRepository, adcid: int
) -> Dict[str, IdentifierObject]:
    """Gets all of the Identifier objects from the identifier database for the
    specified center.

    Args:
      identifiers_repo: identifiers repository
      adcid: the ADCID for the center

    Returns:
      the dictionary mapping from NACCID to Identifier object
    """
    identifiers = {}
    center_identifiers = identifiers_repo.list(adcid=adcid)
    if center_identifiers:
        identifiers = {
            identifier.naccid: identifier for identifier in center_identifiers
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
        raise GearExecutionError("Gear destination not set")

    if dest_container.container_type == "project":
        project_id = dest_container.id
        group_id = dest_container.group
    elif dest_container.container_type in ("subject", "session", "acquisition"):
        project_id = dest_container.parents.project
        group_id = dest_container.parents.group
    else:
        raise GearExecutionError(
            f"Invalid gear destination type {dest_container.container_type}"
        )

    return group_id, project_id


class LegacyIdentifierTransferVisitor(GearExecutionEnvironment):
    """The gear execution visitor for the Legacy identifier transfer gear."""

    def __init__(
        self,
        admin_id: str,
        client: ClientWrapper,
        identifiers_mode: IdentifiersMode,
        legacy_ingest_label: str,
    ):
        super().__init__(client=client)
        self.__admin_id = admin_id
        self.__identifiers_mode: IdentifiersMode = identifiers_mode
        self.__legacy_ingest_label = legacy_ingest_label
        self.__dry_run = client.dry_run

    @classmethod
    def create(
        cls, context: GearContext, parameter_store: Optional[ParameterStore]
    ) -> "LegacyIdentifierTransferVisitor":
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

        client = GearBotClient.create(context=context, parameter_store=parameter_store)

        options = context.config.opts
        admin_id = options.get("admin_group", DefaultValues.NACC_GROUP_ID)
        mode = options.get("identifiers_mode", "prod")
        legacy_ingest_label = options.get(
            "legacy_ingest_label", DefaultValues.LEGACY_PRJ_LABEL
        )

        return LegacyIdentifierTransferVisitor(
            admin_id=admin_id,
            client=client,
            identifiers_mode=mode,
            legacy_ingest_label=legacy_ingest_label,
        )

    def run(self, context: GearContext) -> None:
        """Runs the legacy NACCID transfer gear.

        Args: context: The gear execution context
        """

        assert context, "Gear context expected"

        # Get destination container
        try:
            dest_container = context.config.get_destination_container()
        except ApiException as error:
            raise GearExecutionError(
                f"Error getting destination container: {error}"
            ) from error

        if not dest_container:
            raise GearExecutionError("No destination container found")

        # Get Group and Project IDs, ADCID for group
        group_id, project_id = get_destination_group_and_project(dest_container)
        log.info(f"group_id: {group_id}")

        project = self.proxy.get_project_by_id(project_id=project_id)
        if project is None:
            raise GearExecutionError(f"Unable to find project {project_id}")

        project_adaptor = ProjectAdaptor(project=project, proxy=self.proxy)
        try:
            adcid = project_adaptor.get_pipeline_adcid()
        except ProjectError as error:
            raise GearExecutionError(error) from error
        log.info(f"ADCID: {adcid}")

        # Get all identifiers for given adcid
        try:
            identifiers = get_identifiers(
                identifiers_repo=IdentifiersLambdaRepository(
                    client=LambdaClient(client=create_lambda_client()),
                    mode=self.__identifiers_mode,
                ),
                adcid=adcid,
            )
        except (IdentifierRepositoryError, TypeError) as error:
            raise GearExecutionError(error) from error

        if not identifiers:
            raise GearExecutionError(
                f"Unable to load identifiers for center {group_id} - ADCID {adcid}"
            )

        # Initialize enrollment project adapter
        group = self.proxy.find_group(group_id=group_id)
        if not group:
            raise GearExecutionError(f"Unable to get center group: {group_id}")

        enrollment_project = EnrollmentProject.create_from(project_adaptor)
        log.info(f"Enrollment project: {enrollment_project.label}")

        legacy_ingest_label = self.__legacy_ingest_label
        if len(project_adaptor.label) > len(DefaultValues.ENRL_PRJ_LABEL):
            legacy_ingest_label = (
                self.__legacy_ingest_label
                + project_adaptor.label[len(DefaultValues.ENRL_PRJ_LABEL) :]
            )

        try:
            legacy_project = ProjectAdaptor.create(
                proxy=self.proxy,
                group_id=group_id,
                project_label=legacy_ingest_label,
            )
            log.info(f"Legacy ingest project: {legacy_project.label}")
        except ProjectError as error:
            log.error(f"Could not find {group_id}/{legacy_ingest_label}: {error}")
            legacy_project = None

        forms_store = FormsStore(
            ingest_project=project_adaptor, legacy_project=legacy_project
        )

        options = context.config.opts
        sender_email = options.get("sender_email", "nacchelp@uw.edu")
        target_emails = options.get("target_emails", "nacc_dev@uw.edu")
        target_emails = [x.strip() for x in target_emails.split(",")]

        run(
            identifiers=identifiers,
            enrollment_project=enrollment_project,
            forms_store=forms_store,
            sender_email=sender_email,
            target_emails=target_emails,
            dry_run=self.__dry_run,
        )


def main():
    """The Legacy NACCID transfer gear looks up all of the NACCIDs for a
    center.

    If the center does not already have a Subject with a given NACCID,
    it creates a new subject at that center for that participant.
    """

    GearEngine().create_with_parameter_store().run(
        gear_type=LegacyIdentifierTransferVisitor
    )


if __name__ == "__main__":
    main()
