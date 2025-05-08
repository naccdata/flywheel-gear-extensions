"""Regression curator. Similar to the form curator, but runs a regression test
against the files instead of curating them. Assumes files have already been
curated.

Baseline is a dict mapping each NACCID to a list of dicts containing the
QAF derived values for a given form/visit (e.g. any fields that start
with NACC or key values such as as visit date.)
"""
import logging
from typing import Any, Dict, MutableMapping

from flywheel import Client
from flywheel.models.file_entry import FileEntry
from flywheel.models.subject import Subject
from nacc_attribute_deriver.symbol_table import SymbolTable
from nacc_attribute_deriver.utils.scope import ScopeLiterals
from outputs.errors import MPListErrorWriter, unexpected_value_error

from .curator import Curator

log = logging.getLogger(__name__)


class RegressionCurator(Curator):
    """Runs regression testing against curation."""

    def __init__(self, sdk_client: Client, baseline: MutableMapping,
                 error_writer: MPListErrorWriter) -> None:
        super().__init__(sdk_client)
        self.__baseline = SymbolTable(baseline)
        self.__error_writer = error_writer

    def compare_baseline(self, derived_vars: Dict[str, Any],
                         record: Dict[str, Any]) -> None:
        """Compare the derived variables to the baseline.

        Args:
            derived_vars: Derived variables stored in file metadata
            record: Baseline record to compare to
        """
        # make all lowercase for consistency
        derived_vars = {k.lower(): v for k, v in derived_vars.items()}
        record = {k.lower(): v for k, v in record.items()}

        # compare
        for field, value in derived_vars.items():
            if field not in record:
                log.warning(
                    f"Derived metadata {field} not in baseline, skipping")
                continue

            # convert booleans to 0/1
            if isinstance(value, bool):
                value = int(value)

            # compare as strings for simplicity
            value = str(value)
            expected = str(record[field])
            if value != expected:
                msg = (f"{record['naccid']} {record['visitdate']} " +
                       f"field {field}: derived value {value} does not " +
                       f"match expected value {expected}")
                log.info(msg)
                self.__error_writer.write(
                    unexpected_value_error(
                        field=field,
                        value=value,  # type: ignore
                        expected=expected,
                        message=msg))

    def execute(self, subject: Subject, file_entry: FileEntry,
                table: SymbolTable, scope: ScopeLiterals) -> None:
        """Perform contents of curation. Assumes UDS data.

        Args:
            subject: Subject the file belongs to
            file_entry: FileEntry of file being curated
            table: SymbolTable containing file/subject metadata.
            scope: The scope of the file being curated
        """
        # skip if not UDS, no derived variables, or no visitdate found
        if scope != 'uds':
            log.info(f"{file_entry.name} is a not an UDS form, skipping")
            return

        derived_vars = table.get('file.info.derived', None)
        if (not derived_vars or not any(x.lower().startswith('nacc')
                                        for x in derived_vars)):
            log.info(
                f"No derived variables found for {file_entry.name}, skipping")
            return

        visitdate = table.get("file.info.forms.json.visitdate")
        if not visitdate:
            log.info(f"No visitdate found for {file_entry.name}, skipping")
            return

        # ensure in QAF baseline - if not affiliate, report error
        key = f'{subject.label}_{visitdate}'
        record = self.__baseline.get(key)
        if not record:
            if 'affiliate' in subject.tags:
                log.info(f"{subject.label} is an affiliate, skipping")
                return

            msg = (f"Could not find matching record for {file_entry.name} " +
                   f"in baseline file with NACCID and visitdate: {key}")
            log.warning(msg)
            self.__error_writer.write(
                unexpected_value_error(
                    field='naccid',
                    value=None,  # type: ignore
                    expected=key,
                    message=msg))
            return

        self.compare_baseline(derived_vars, record)
