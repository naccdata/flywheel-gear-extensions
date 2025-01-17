"""Defines Legacy Sanity Check."""

import json
import logging

from typing import List

import flywheel
from datastore.forms_store import FormQueryArgs, FormStore
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from key.keys import (
    DefaultValues,
    FieldNames,
    SysErrorCodes,
    preprocess_errors,
)
from notifications.email import EmailClient, create_ses_client
from outputs.errors import ListErrorWriter, preprocessing_error
from preprocess.preprocessor import FormProjectConfigs

log = logging.getLogger(__name__)


class LegacySanityChecker:
    """Class to run sanity checks on legacy retrospective projects."""

    def __init__(self,
                 form_store: FormStore,
                 form_configs: FormProjectConfigs,
                 error_writer: ListErrorWriter,
                 legacy_project: ProjectAdaptor):
        """Initializer."""
        self.__form_store = form_store
        self.__form_configs = form_configs
        self.__error_writer = error_writer
        self.__legacy_project = legacy_project

    def check_multiple_ivp(self,
                           subject_lbl: str,
                           module: str) -> bool:
        """Checks that a subject does not have multiple
        conflicting initial visits

        Args:
            subject_lbl: The subject (e.g. the NACCID)
            module: The module (e.g. UDS)
        Returns:
            True if if passes the check, False otherwise
        """
        log.info(f'Checking for multiple visits for {subject_lbl} '
                 + f' module {module}')

        module_configs = self.__form_configs.module_configs.get(module, None)
        if not module_configs:
            raise ValueError(f"Unrecognized module: {module}")

        initial_packet_query = FormQueryArgs(
            subject_lbl=subject_lbl,
            module=module,
            search_col=FieldNames.PACKET,
            search_val=module_configs.initial_packets,
            search_op=DefaultValues.FW_SEARCH_OR)

        # query retrospective initial visits
        init_legacy_packets = self.__form_store.query_legacy_project(
                **initial_packet_query.model_dump())

        # first check there aren't somehow multiple initial retrospective visits
        num_legacy = len(init_legacy_packets) if init_legacy_packets else 0
        if num_legacy > 1:
            log.error(f"Subject {subject_lbl} has multiple retrospective initial "
                      + f"visit packets for {module} {num_initial_packets}")
            self.__error_writer.write(
                FileError(
                    error_type='error',
                    error_code=SysErrorCodes.MULTIPLE_IVP,
                    value=f'{num_legacy} visits',
                    message=preprocess_errors[SysErrorCodes.MULTIPLE_IVP]
                )
            )
            return False
        # if there are no retrospective legacy initial packets, we're good
        elif num_legacy == 0:
            return  True

        log.info("Retrsopective project has an initial visit packet "
                 + "checking ingest project")

        # next compare against ingest visits
        init_packets = self.__form_store.query_project(
             **initial_packet_query.model_dump())

        # if no initial packets, then we're good to go
        if not init_packets:
            return True

        # it not UDS or somehow more than one initial packet exists
        # we have a problem, report error
        if module.lower() != 'uds' or len(init_packets):
            log.error(f"Subject {subject_lbl} already has initial "
                      + f"visit packet(s) for {module} in ingest project")
            self.__error_writer.write(
                FileError(
                    error_type='error',
                    error_code=SysErrorCodes.MULTIPLE_IVP,
                    value=f'{len(init_packets)} visits in ingest',
                    message=preprocess_errors[SysErrorCodes.MULTIPLE_IVP]
                )
            )
            return False

        # otherwise, for UDS we need to check if it is an I4,
        # which is allowed, otherwise also fail the check
        record = init_packets[0].get_visit_data(
            init_packet['file.name'],
            init_packet['file.parents.acquisition'])

        if not record:
            raise ValueError(
                f"Error reading previous visit file {initial_packet['file.name']}"
            )
        if record[FieldNames.PACKET] != DefaultValues.UDS_I4_PACKET:
            log.error(f"Subject {subject_lbl} already has non-I4 initial "
                      + f"visit packet(s) for {module} in ingest project")
            self.__error_writer.write(
                FileError(
                    error_type='error',
                    error_code=SysErrorCodes.MULTIPLE_IVP,
                    value=f'{len(init_packets)} non-I4 visits in ingest',
                    message=preprocess_errors[SysErrorCodes.MULTIPLE_IVP]
                )
            )
            return False

        # ingest project would only accept an I4 if it was valid, so we
        # don't need to check further from here
        log.info("Ingest project has singular I4 packet, okay")
        return True

    def check_duplicate_visit(self,
                              subject_lbl: str,
                              module: str) -> bool:
        """Check for duplicates visits. Two visits are considered
        duplicates if all of the packet, visitnum, and visitdate
        are the same.

        Args:
            subject_lbl: The subject (e.g. the NACCID)
            module: The module (e.g. UDS)
        Returns:
            True if if passes the check, False otherwise
        """
        log.info(f'Checking for duplicate visits for {subject_lbl} '
                 + f' module {module}')

        module_configs = self.__form_configs.module_configs.get(module, None)
        if not module_configs:
            raise ValueError(f"Unrecognized module: {module}")

        duplicates_query = FormQueryArgs(
            subject_lbl=subject_lbl,
            module=module,
            search_col=FieldNames.PACKET,
            search_val=None,
            search_op=None,
            extra_columns=[FieldNames.VISITNUM, FieldNames.VISITDATE],
            find_all=True)

        ingest_results = self.__form_store.query_project(
             **duplicates_query.model_dump())
        retro_results = self.__form_store.query_project(
             **duplicates_query.model_dump())

        # if there are no visits for the module/packet in one of the projects
        # this automatically passes
        if not ingest_results or not restro_results:
            log.info("No results found for one or more projects, "
                     + "automatically passes")
            return True

        # otherwise we need to compare duplicates. store each record's
        # visitnum/visitdate in a tuple and compare between the projects
        visitnum_lbl = \
            f'{DefaultValues.FORM_METADATA_PATH}.{FieldNames.VISITNUM}'
        visitdate_lbl = \
            f'{DefaultValues.FORM_METADATA_PATH}.{FieldNames.VISITDATE}'

        ingest_records = [(record[visitnum_lbl], record[visitdate_lbl])
                          for record in ingest_results]
        retro_records = [(record[visitnum_lbl], record[visitdate_lbl])
                          for record in retro_results]

        found_duplicates = False
        for record in ingest_record:
            if record in retro_records:
                found_duplicates = True
                duplicate_val = f'subject: {subject_lbl} module: {module}, ' \
                    + f'packet: {packet} visitnum: {record[0]}, '
                    + f'visitdate: {record[1]}'

                log.error(f"Duplicate records found for {duplicate_val}")
                self.__error_writer.write(
                    FileError(
                        error_type='error',
                        error_code='duplicate-visits',
                        value=duplicate_val,
                        message="Duplicate records found between ingest "
                            + "and retrospective projects"
                    )
                )

        return found_duplicates

    def run_all_checks(self) -> None:
        """Runs all sanity checks for each subject/module in the
        retrospective project
        """
        module_configs = self.__form_configs.module_configs
        for subject in self.__legacy_project.subjects():
            for module in module_configs:
                if not self.check_multiple_ivp(subject.label, module):
                    continue
                self.check_conflicting_visits(subject.label, module)

    def send_email(sender_email: str,
                   target_emails: List[str],
                   group_lbl: str):
        """Send a raw email notifying of the error

        Args:
            sender_email: The sender email
            target_emails: The target email(s)
            group_lbl: The group label
        """
        client = EmailClient(client=create_ses_client(),
                             source=sender_email)

        subject = f'{self.__project.label} Sanity Check Failure'
        body = f'Project {self.__project.label} for {group_lbl} failed '
             + 'the following legacy sanity checks:\n'
        body += json.dumps(self.__error_writer.errors())

        client.send_raw(destinations=target_emails,
                        subject=subject,
                        body=body)
