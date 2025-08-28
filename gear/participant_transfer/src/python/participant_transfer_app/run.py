"""Entry script for Manage Participant Transfer."""

import logging
from typing import Optional

from enrollment.enrollment_project import EnrollmentProject
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
)
from identifiers.model import IdentifiersMode
from inputs.parameter_store import ParameterStore
from keys.keys import DefaultValues
from lambdas.lambda_function import LambdaClient, create_lambda_client
from utils.utils import parse_string_to_list

from participant_transfer_app.main import run

log = logging.getLogger(__name__)


class ParticipantTransferVisitor(GearExecutionEnvironment):
    """Visitor for the Manage Participant Transfer gear."""

    def __init__(
        self,
        client: ClientWrapper,
        admin_id: str,
        enroll_project_path: str,
        ptid: str,
        identifiers_mode: IdentifiersMode,
    ):
        super().__init__(client=client)
        self.__admin_id = admin_id
        self.__enroll_project_path = enroll_project_path
        self.__ptid = ptid
        self.__identifiers_mode: IdentifiersMode = identifiers_mode

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "ParticipantTransferVisitor":
        """Creates a Manage Participant Transfer execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """

        assert parameter_store, "Parameter store expected"

        client = GearBotClient.create(
            context=context, parameter_store=parameter_store)

        enroll_project_path = context.config.get("enrollment_project")
        if not enroll_project_path:
            raise GearExecutionError(
                "Missing required gear config enrollment_project")

        ptid = context.config.get("participant_id")
        if not ptid:
            raise GearExecutionError(
                "Missing required gear config participant_id")

        mode = context.config.get("database_mode", "prod")
        admin_id = context.config.get(
            "admin_group", DefaultValues.NACC_GROUP_ID)

        return ParticipantTransferVisitor(
            client=client,
            admin_id=admin_id,
            enroll_project_path=enroll_project_path,
            ptid=ptid,
            identifiers_mode=mode,
        )

    def run(self, context: GearToolkitContext) -> None:
        project = self.proxy.lookup(self.__enroll_project_path)
        if not project:
            raise GearExecutionError(
                f"Unable to find enrollment project: {self.__enroll_project_path}"
            )

        enroll_project = EnrollmentProject(project=project, proxy=self.proxy)

        identifiers_repo = IdentifiersLambdaRepository(
            client=LambdaClient(client=create_lambda_client()),
            mode=self.__identifiers_mode,
        )

        admin_group = self.admin_group(admin_id=self.__admin_id)
        datatypes = parse_string_to_list(
            context.config.get("datatypes", "form,scan,dicom")
        )
        source_email = context.config.get("sender_email", "naccmail@uw.edu")
        target_emails = context.config.get("target_emails", "nacchelp@uw.edu")
        target_emails = [x.strip() for x in target_emails.split(",")]

        run(
            proxy=self.proxy,
            admin_group=admin_group,
            enroll_project=enroll_project,
            ptid=self.__ptid,
            identifiers_repo=identifiers_repo,
            datatypes=datatypes,
            source_email=source_email,
            dry_run=self.client.dry_run,
        )


def main():
    """Main method for Manage Participant Transfer."""

    GearEngine.create_with_parameter_store().run(
        gear_type=ParticipantTransferVisitor)


if __name__ == "__main__":
    main()
