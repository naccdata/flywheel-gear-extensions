"""Defines Legacy Sanity Check."""

import logging

from typing import List

import flywheel
from datastore.forms_store import FormsStoreGeneric
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from key.keys import (
    DefaultValues,
    FieldNames,
    SysErrorCodes,
    preprocess_errors,
)
from outputs.errors import ListErrorWriter, preprocessing_error
from preprocess.preprocessor import FormProjectConfigs

log = logging.getLogger(__name__)


class LegacySanityChecker:
    """Class to run sanity checks on legacy retrospective projects."""

    def __init__(self,
                 form_store: FormStoreGeneric,
                 form_configs: FormProjectConfigs,
                 error_writer: ListErrorWriter):
        """Initializer."""
        self.__form_store = form_store
        self.__form_configs = form_configs
        self.__error_writer = error_writer

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

    def run_all_checks(self, subject_lbl: str) -> None:
        """Runs all sanity checks on the given subject.

        Args:
            subject_lbl: The subject's label
        """
        module_configs = self.__form_configs.module_configs
        for module in module_configs:
            self.check_multiple_ivp(subject_lbl, module)


def run(*,
        proxy: FlywheelProxy,
        sanity_checker: LegacySanityChecker,
        project: flywheel.Project):
    """Runs the Legacy Sanity Check process for each subject
    in the project.

    Args:
        proxy: the proxy for the Flywheel instance
        sanity_checker: The LegacySanityChecker
        project: The Flywheel project to evaluate
    """
    for subject in project.subjects():
        sanity_checker.run_all_checks(subject.label)
