"""Defines Legacy Sanity Check."""

import json
import logging

from typing import List

import flywheel
from datastore.forms_store import FormStore
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
                           module: str) -> None:
        """Checks that a subject does not have multiple
        initial visits

        Args:
            subject_lbl: The subject (NACCID)
            module: The module (e.g. UDS)
        """
        log.info(f'Checking for multiple visits for {subject_lbl} '
                 + f' module {module}')

        module_configs = self.__form_configs.module_configs.get(module, None)
        if not module_configs:
            raise ValueError(f"Unrecognized module: {module}")

        initial_packets = self.__form_store.query_project(
            subject_lbl=subject_lbl,
            module=module,
            search_col=FieldNames.PACKET,
            search_val=module_configs.initial_packets,
            search_op=DefaultValues.FW_SEARCH_OR)  # type: ignore

        num_initial_packets = len(initial_packets) if initial_packets else 0
        if num_initial_packets > 1:
            log.error(f"Subject {subject_lbl} has multiple initial visit packets "
                      + f"for {module} {num_initial_packets}, writing errors")
            self.__error_writer.write(
                FileError(
                    error_type='error',
                    error_code=SysErrorCodes.MULTIPLE_IVP,
                    value=f'{num_initial_packets} visits',
                    message=preprocess_errors[SysErrorCodes.MULTIPLE_IVP]
                )
            )

    def run_all_checks(self) -> None:
        """Runs all sanity checks for each subject/module in the
        retrospective project
        """
        module_configs = self.__form_configs.module_configs
        for subject in self.__legacy_project.subjects():
            for module in module_configs:
                self.check_multiple_ivp(subject.label, module)


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
