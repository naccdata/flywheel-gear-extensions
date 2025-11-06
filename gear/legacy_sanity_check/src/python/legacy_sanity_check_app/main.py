"""Defines Legacy Sanity Check."""

import logging
from typing import List

from configs.ingest_configs import FormProjectConfigs, ModuleConfigs
from datastore.forms_store import FormQueryArgs, FormsStore
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from keys.keys import (
    DefaultValues,
    MetadataKeys,
    SysErrorCodes,
)
from nacc_common.error_models import FileError
from nacc_common.field_names import FieldNames
from notifications.email import EmailClient, create_ses_client
from outputs.error_writer import ListErrorWriter
from outputs.errors import (
    preprocess_errors,
)

log = logging.getLogger(__name__)


class LegacySanityChecker:
    """Class to run sanity checks on legacy retrospective projects."""

    def __init__(
        self,
        form_store: FormsStore,
        form_configs: FormProjectConfigs,
        error_writer: ListErrorWriter,
        legacy_project: ProjectAdaptor,
    ):
        """Initializer."""
        self.__form_store = form_store
        self.__form_configs = form_configs
        self.__error_writer = error_writer
        self.__legacy_project = legacy_project

    def check_multiple_ivp(
        self, subject_lbl: str, module: str, module_configs: ModuleConfigs
    ) -> bool:
        """Checks that a subject does not have multiple conflicting initial
        visits.

        Args:
            subject_lbl: The subject (e.g. the NACCID)
            module: The module (e.g. UDS)
            module_configs: Form ingest configs for the module

        Returns:
            True if if passes the check, False otherwise
        """
        log.info(f"Checking for multiple visits in {module}")

        initial_packet_query = FormQueryArgs(
            subject_lbl=subject_lbl,
            module=module,
            legacy=True,
            search_col=FieldNames.PACKET,
            search_val=module_configs.initial_packets,
            search_op=DefaultValues.FW_SEARCH_OR,
        )

        # query retrospective initial visits
        init_legacy_packets = self.__form_store.query_form_data(
            **initial_packet_query.model_dump()
        )

        # first check there aren't somehow multiple initial retrospective visits
        num_legacy = len(init_legacy_packets) if init_legacy_packets else 0
        if num_legacy > 1:
            log.error(
                "Multiple retrospective initial visit packets "
                + f"found for {module}: {num_legacy}"
            )
            self.__error_writer.write(
                FileError(
                    error_type="error",  # type: ignore
                    error_code=SysErrorCodes.MULTIPLE_IVP,  # type: ignore
                    value=f"{num_legacy} initial visits in retrospective",
                    message=preprocess_errors[SysErrorCodes.MULTIPLE_IVP],
                )
            )
            return False

        log.info(
            "Retrospective project has an initial visit packet, "
            + "checking ingest project"
        )

        # next compare against ingest visits
        initial_packet_query.legacy = False
        init_packets = self.__form_store.query_form_data(
            **initial_packet_query.model_dump()
        )

        # if no initial packets, then we're good to go
        if not init_packets:
            log.info("Ingest project has no initial visits, passes check")
            return True

        # it not UDS or somehow more than one initial packet exists
        # we have a problem, report error
        if module.upper() != DefaultValues.UDS_MODULE or len(init_packets) > 1:
            log.error(
                "Initial visit packet(s) already exist for "
                + f"{module} in ingest project"
            )
            self.__error_writer.write(
                FileError(
                    error_type="error",  # type: ignore
                    error_code=SysErrorCodes.MULTIPLE_IVP,  # type: ignore
                    value=f"{len(init_packets)} initial visits in ingest",
                    message=preprocess_errors[SysErrorCodes.MULTIPLE_IVP],
                )
            )
            return False

        # otherwise, for UDS we need to check if it is an I4,
        # which is allowed, otherwise also fail the check
        packet_lbl = f"{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.PACKET}"

        if init_packets[0][packet_lbl] != DefaultValues.UDS_I4_PACKET:
            log.error(
                "Non-I4 initial visit packet already exists for"
                + f"{module} in ingest project"
            )
            self.__error_writer.write(
                FileError(
                    error_type="error",  # type: ignore
                    error_code=SysErrorCodes.MULTIPLE_IVP,  # type: ignore
                    value=f"{len(init_packets)} non-I4 visits in ingest",
                    message=preprocess_errors[SysErrorCodes.MULTIPLE_IVP],
                )
            )
            return False

        # ingest project would only accept an I4 if it was valid, so we
        # don't need to check further from here
        log.info("Ingest project has singular I4 packet, passes check")
        return True

    def check_duplicate_visit(
        self, subject_lbl: str, module: str, module_configs: ModuleConfigs
    ) -> bool:
        """Check for duplicates visits. Two visits are considered duplicates if
        all of the packet, visitnum, and visitdate are the same.

        Args:
            subject_lbl: The subject (e.g. the NACCID)
            module: The module (e.g. UDS)
        Returns:
            True if if passes the check, False otherwise
        """
        log.info(f"Checking for duplicate visits in {module}")

        visitdate = module_configs.date_field
        legacy_visitdate = (
            module_configs.legacy_module.date_field
            if module_configs.legacy_module
            else visitdate
        )

        duplicates_query = FormQueryArgs(
            subject_lbl=subject_lbl,
            module=module,
            legacy=False,
            search_col=FieldNames.PACKET,
            extra_columns=[FieldNames.VISITNUM, visitdate],
            find_all=True,
        )

        ingest_results = self.__form_store.query_form_data(
            **duplicates_query.model_dump()
        )

        duplicates_query.extra_columns = [
            FieldNames.VISITNUM, legacy_visitdate]
        duplicates_query.legacy = True
        retro_results = self.__form_store.query_form_data(
            **duplicates_query.model_dump()
        )

        # if there are no visits for the module/packet in one of the projects
        # this automatically passes
        if not ingest_results or not retro_results:
            log.info(
                "No visits found for one or both projects, " + "automatically passes"
            )
            return True

        # otherwise we need to compare duplicates. store each record's
        # packet/visitnum/visitdate in a tuple and compare between the projects
        packet_lbl = f"{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.PACKET}"
        visitnum_lbl = f"{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.VISITNUM}"
        visitdate_lbl = f"{MetadataKeys.FORM_METADATA_PATH}.{visitdate}"
        legacy_visitdate_lbl = f"{MetadataKeys.FORM_METADATA_PATH}.{legacy_visitdate}"

        ingest_records = [
            (record[packet_lbl], record[visitnum_lbl], record[visitdate_lbl])
            for record in ingest_results
        ]
        retro_records = [
            (record[packet_lbl], record[visitnum_lbl],
             record[legacy_visitdate_lbl])
            for record in retro_results
        ]

        no_duplicates = True
        for record in retro_records:
            if record in ingest_records:
                no_duplicates = False
                duplicate_val = (
                    f"subject: {subject_lbl} module: {module}, "
                    + f"packet: {record[0]} visitnum: {record[1]}, "
                    + f"visitdate: {record[2]}"
                )

                log.error(f"Duplicate records found for {duplicate_val}")
                self.__error_writer.write(
                    FileError(
                        error_type="error",  # type: ignore
                        error_code="duplicate-visits",  # type: ignore
                        value=duplicate_val,
                        message="Duplicate records found between ingest "
                        + "and retrospective projects",
                    )
                )

        if no_duplicates:
            log.info("No duplicates found, passes check")

        return no_duplicates

    def run_all_checks(self, subject_lbl: str, module: str) -> bool:
        """Runs all sanity checks for the given subject and module.

        Args:
            subject_lbl: Subject label to run checks on
            module: Module to run checks on

        Returns:
            Whether or not checks were successful
        """
        log.info(
            f"Running legacy sanity checks for subject {subject_lbl}"
            + f" and module {module}"
        )

        module_configs = self.__form_configs.module_configs.get(module, None)
        if not module_configs:
            raise ValueError(f"Unrecognized module: {module}")

        if not self.check_multiple_ivp(subject_lbl, module, module_configs):
            return False

        return self.check_duplicate_visit(subject_lbl, module, module_configs)

    def send_email(
        self, sender_email: str, target_emails: List[str], group_lbl: str
    ) -> None:
        """Send a raw email notifying target emails of the error.

        Args:
            sender_email: The sender email
            target_emails: The target email(s)
            group_lbl: The group label
        """
        client = EmailClient(client=create_ses_client(), source=sender_email)

        project_lbl = self.__legacy_project.label
        subject = f"{project_lbl} Sanity Check Failure"
        body = (
            f"Project {project_lbl} for {group_lbl} failed "
            "the following legacy sanity checks:\n\n"
            f"{self.__error_writer.errors().model_dump_json(by_alias=True, indent=4)}"
        )

        client.send_raw(destinations=target_emails, subject=subject, body=body)
