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
from utils.decorators import api_retry

from .curator import Curator

log = logging.getLogger(__name__)


class RegressionCurator(Curator):
    """Runs regression testing against curation."""

    def __init__(self,
                 sdk_client: Client,
                 qaf_baseline: MutableMapping,
                 mqt_baseline: MutableMapping,
                 error_writer: MPListErrorWriter) -> None:
        super().__init__(sdk_client)
        self.__qaf_baseline = SymbolTable(qaf_baseline)
        self.__mqt_baseline = SymbolTable(mqt_baseline)

        self.__error_writer = error_writer

    def compare_baseline(self, found_vars: Dict[str, Any],
                         record: Dict[str, Any],
                         prefix: str) -> None:
        """Compare derived/curated variables to the baseline.

        Args:
            found_vars: Found variables to compare to baseline
            record: Baseline record to compare to
            prefix: Field prefix
        """
        # make all lowercase for consistency and SymbolTables for indexing
        found_vars = SymbolTable({k.lower(): v for k, v in found_vars.items()})
        record = SymbolTable({k.lower(): v for k, v in record.items()})

        # compare
        for field, value in found_vars.items():
            if field not in record:
                log.warning(
                    f"Field {field} not in baseline, skipping")
                continue

            # convert booleans to 0/1
            if isinstance(value, bool):
                value = int(value)

            # compare as strings for simplicity
            value = str(value)
            expected = str(record[field])
            if value != expected:
                msg = record["naccid"]
                if 'visitdate' in record:
                    msg = f"{msg} {record['visitdate']}"

                if prefix.startswith('file'):
                    msg = f"{record['naccid']} {record['visitdate']}"
                else:
                    msg = f"{record['naccid']}"

                msg = (f"{msg} field {field}: found value {value} " +
                       f"does not match expected value {expected}")
                log.info(msg)
                self.__error_writer.write(
                    unexpected_value_error(
                        field=f'{prefix}.{field}',
                        value=value,  # type: ignore
                        expected=expected,
                        message=msg))

    def execute(self, subject: Subject, file_entry: FileEntry,
                table: SymbolTable, scope: ScopeLiterals) -> None:
        """Performs file-level regression testing.

        Args:
            subject: Subject the file belongs to
            file_entry: FileEntry of file being curated
            table: SymbolTable containing file/subject metadata.
            scope: The scope of the file being curated
        """
        # each subject in the baseline is mapped to a list of ordered records;
        # for UDS need to map the correct record based on visitdate
        # otherwise just grab the most recent record, which is assumed to have
        # all the derived variables propogated to it
        derived_vars = table.get('file.info.derived', None)
        # if no derived variables, skip
        if (not derived_vars or not any(x.lower().startswith('nacc')
                                        for x in derived_vars)):
            log.info("No file derived variables, skipping")
            return

        if subject.label not in self.__qaf_baseline:
            if not derived_vars.get('affiliate', False):
                msg = (
                    f"Subject {subject.label} not found in baseline QAF and not affiliate"
                )
                log.warning(msg)
                self.__error_writer.write(
                    unexpected_value_error(
                        field='naccid',
                        value=None,  # type: ignore
                        expected=subject.label,
                        message=msg))
            return

        record = None
        expected = subject.label

        if scope == 'uds':
            visitdate = table['file.info.forms.json.visitdate']
            expected = f"{expected} {visitdate}"
            for r in self.__qaf_baseline[subject.label]:
                if visitdate == r['visitdate']:
                    record = r
                    break
        else:
            record = self.__qaf_baseline[subject.label][-1]

        if not record:
            msg = (f"Could not find matching record for {file_entry.name} " +
                   f"in baseline QAF file with attributes {expected}")
            log.warning(msg)
            self.__error_writer.write(
                unexpected_value_error(
                    field='naccid',
                    value=None,  # type: ignore
                    expected=expected,
                    message=msg))
            return

        self.compare_baseline(derived_vars, record, prefix='file.info.derived')

    @api_retry
    def post_process(self, subject: Subject,
                     processed_files: List[str]) -> None:
        """Run post-processing on the entire subject. Compares subject.info.

        Args:
            subject: Subject to pre-process
            processed_files: List of file IDs that were processed
        """
        subject = subject.reload()
        if not subject.info:
            log.info("No subject derived variables, skipping")
            return

        # means subject hasn't been curated before - might not
        # be worth reporting in the long run but for now over report
        if subject.label not in self.__mqt_baseline:
            msg = f"Could not find curated subject {subject.label} in MQT baseline"
            log.warning(msg)

            self.__error_writer.write(
                unexpected_value_error(
                    field='subject.label',
                    value=None,  # type: ignore
                    expected=subject.label,
                    message=msg))
            return

        record = self.__mqt_baseline[subject.label]
        self.compare_baseline(subject.info, record, prefix='subject.info')
