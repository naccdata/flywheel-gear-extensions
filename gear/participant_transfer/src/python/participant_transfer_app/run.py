"""Entry script for Manage Participant Transfer."""

import logging
from typing import List, Optional

from enrollment.enrollment_project import EnrollmentProject
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
from identifiers.model import IdentifiersMode
from inputs.parameter_store import ParameterStore
from keys.keys import DefaultValues
from lambdas.lambda_function import LambdaClient, create_lambda_client
from notifications.email import EmailClient, create_ses_client
from participant_transfer_app.main import run
from utils.utils import parse_string_to_list

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
        copy_only: bool,
    ):
        super().__init__(client=client)
        self.__admin_id = admin_id
        self.__enroll_project_path = enroll_project_path
        self.__ptid = ptid
        self.__identifiers_mode: IdentifiersMode = identifiers_mode
        self.__copy_only = copy_only

    @classmethod
    def create(
        cls,
        context: GearContext,
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

        client = GearBotClient.create(context=context, parameter_store=parameter_store)

        options = context.config.opts
        enroll_project_path = options.get("enrollment_project")
        if not enroll_project_path:
            raise GearExecutionError("Missing required gear config enrollment_project")

        ptid = options.get("participant_id")
        if not ptid:
            raise GearExecutionError("Missing required gear config participant_id")

        mode = options.get("database_mode", "prod")
        admin_id = options.get("admin_group", DefaultValues.NACC_GROUP_ID)
        copy_only = options.get("copy_only", False)

        return ParticipantTransferVisitor(
            client=client,
            admin_id=admin_id,
            enroll_project_path=enroll_project_path,
            ptid=ptid,
            identifiers_mode=mode,
            copy_only=copy_only,
        )

    def run(self, context: GearContext) -> None:
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

        options = context.config.opts
        admin_group = self.admin_group(admin_id=self.__admin_id)
        datatypes = parse_string_to_list(options.get("datatypes", "form,scan,dicom"))

        sender_email = options.get("sender_email", "nacc_dev@uw.edu")
        target_emails = options.get("target_emails", "nacchelp@uw.edu")
        target_emails = [x.strip() for x in target_emails.split(",")]

        gear_name = self.gear_name(context, "participant-transfer")
        job_id = self.get_job_id(context=context, gear_name=gear_name)
        try:
            success = run(
                proxy=self.proxy,
                admin_group=admin_group,
                enroll_project=enroll_project,
                ptid=self.__ptid,
                identifiers_repo=identifiers_repo,
                datatypes=datatypes,
                copy_only=self.__copy_only,
                dry_run=self.client.dry_run,
            )

            self.send_email(
                sender_email=sender_email,
                target_emails=target_emails,
                project=enroll_project,
                ptid=self.__ptid,
                status="SUCCESS" if success else "NEEDS REVIEW",
                job_id=job_id,
            )
        except GearExecutionError as error:
            self.send_email(
                sender_email=sender_email,
                target_emails=target_emails,
                project=enroll_project,
                ptid=self.__ptid,
                status="FAILED",
                job_id=job_id,
            )
            raise GearExecutionError(error) from error

    def send_email(
        self,
        *,
        sender_email: str,
        target_emails: List[str],
        project: EnrollmentProject,
        ptid: str,
        status: str,
        job_id: Optional[str],
    ) -> None:
        """Send a raw email notifying target emails of the gear failure.

        Args:
            sender_email: The sender email
            target_emails: The target email(s)
            project: enrollment project in Flywheel for receiving center
            ptid: PTID of transfer request
            status: Transfer status (FAILED, NEEDS REVIEW, SUCCESS)
            job_id: participant-transfer gear job id
        """

        if self.client.dry_run:
            log.info("Dry run, not sending email")
            return

        client = EmailClient(client=create_ses_client(), source=sender_email)

        # client.host is like https://naccdata.flywheel.io:443/api
        host_url = f"{self.client.host.rsplit(':', 1)[0]}"
        job_log_url = f"{host_url}/#/jobs/{job_id}" if job_id else f"{host_url}/#/jobs/"
        project_url = f"{host_url}/#/projects/{project.id}/info"

        subject = (
            f"Participant Transfer Status for {project.group}/{project.label}: {status}"
        )

        next_steps = ""
        if status == "FAILED":
            next_steps = "Correct the errors and retry the transfer."
        elif status == "SUCCESS":
            next_steps = (
                "Review the transferred participant data in Flywheel "
                "and notify the centers about the transfer completion."
            )
        else:
            next_steps = (
                "This transfer completed with warnings, "
                "check the warnings in the gear job log "
                "and review the transferred participant data in Flywheel.\n"
                "If everything looks fine, "
                "notify the centers about the transfer completion."
            )

        body = (
            f"\n\nPlease review the participant-transfer gear run details below "
            f"and take necessary actions."
            f"\n\tStatus: {status}"
            f"\n\tPTID: {ptid}"
            f"\n\tEnrollment project: {project.group}/{project.label}"
            f"\n\tEnrollment project URL: {project_url}"
            f"\n\tGear job log: {job_log_url}"
            "\n\nCheck the job log for more details on any errors or warnings."
            "\n\n**Next steps:"
            f"\n{next_steps}\n\n"
        )

        client.send_raw(destinations=target_emails, subject=subject, body=body)


def main():
    """Main method for Manage Participant Transfer."""

    GearEngine.create_with_parameter_store().run(gear_type=ParticipantTransferVisitor)


if __name__ == "__main__":
    main()
