"""Regression curator. Similar to the form curator, but runs a regression test
against the files instead of curating them. Assumes files have already been
curated.

Baseline is a dict mapping each NACCID to a list of dicts containing the
QAF derived values for a given form/visit (e.g. any fields that start
with NACC or key values such as as visit date.)
"""
import logging
from typing import Any, Dict, MutableMapping

from curator.curator import Curator
from flywheel import Client
from flywheel.models.file_entry import FileEntry
from flywheel.models.subject import Subject
from nacc_attribute_deriver.symbol_table import SymbolTable
from nacc_attribute_deriver.utils.scope import ScopeLiterals
from outputs.errors import MPListErrorWriter, unexpected_value_error

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
                log.warning(f"Derived metadata {field} not in baseline, skipping")
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
                    unexpected_value_error(field=field,
                                           value=value,
                                           expected=expected,
                                           message=msg))

    def execute(self, subject: Subject, file_entry: FileEntry,
                table: SymbolTable, scope: ScopeLiterals) -> None:
        """Perform contents of curation.

        Args:
            subject: Subject the file belongs to
            file_entry: FileEntry of file being curated
            table: SymbolTable containing file/subject metadata.
            scope: The scope of the file being curated
        """
        if subject.label not in self.__baseline:
            log.warning(
                f"Subject {subject.label} not found in baseline, skipping")
            return

        # each subject in the baseline is mapped to a list of ordered records;
        # for UDS need to map the correct record based on visitdate
        # otherwise just grab the most recent record, which is assumed to have
        # all the derived variables propogated to it
        # additionally, if the scope is UDS, then we compare derived variables
        # on the file otherwise, compare derived variables on the subject

        # TODO: in general need to figure out a better mapping. since everything
        # is lumped together this will likely check the same subject-level variables
        # multiple times over. maybe it's better to only look at file-level derived
        # variables? which will result in only UDS being looked at, which
        # might be fine
        derived_vars = table.get('file.info.derived', None)
        # if no derived variables, skip
        if (not derived_vars or not any(x.lower().startswith('nacc')
                                        for x in derived_vars)):
            log.info("No derived variables, skipping")
            return

        record = None
        # derived_vars = None
        if scope == 'uds':
            #derived_vars = table.get('file.info.derived', None)
            for r in self.__baseline[subject.label]:
                if table['file.info.forms.json.visitdate'] == r['visitdate']:
                    record = r
                    break
        else:
            #derived_vars = table.get('subject.info.derived', None)
            record = self.__baseline[subject.label][-1]

        if not record:
            log.warning(
                f"Could not find matching record for {file_entry.name} " +
                "in baseline file")
            return

        self.compare_baseline(derived_vars, record)
