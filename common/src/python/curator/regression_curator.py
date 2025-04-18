"""
Regression curator. Similar to the form curator,
but runs a regression test against the files instead
of curating them. Assumes files have already been curated.

Baseline is a dict mapping each NACCID to a list of dicts
containing the QAF derived values for a given form/visit
(e.g. any fields that start with NACC or key values such as
as visit date.)
"""
from typing import Any, Dict
from nacc_attribute_deriver.symbol_table import SymbolTable
from nacc_attribute_deriver.utils.scope import ScopeLiterals

from outputs.errors import MPListErrorWriter, unexpected_value_error

from .curator import Curator


class RegressionCurator(Curator):
    """Runs regression testing against curation."""

    def __init__(self,
                 sdk_client: Client,
                 baseline: Dict[str, Any],
                 error_writer: MPListErrorWriter) -> None:
        super().__init__(sdk_client)
        self.__baseline = SymbolTable(baseline)
        self.__error_writer = error_writer

    def execute(self,
                subject: Subject,
                file_entry: FileEntry,
                table: SymbolTable,
                scope: ScopeLiterals) -> None:
        """Perform contents of curation.
    
        Args:
            subject: Subject the file belongs to
            file_entry: FileEntry of file being curated
            table: SymbolTable containing file/subject metadata.
            scope: The scope of the file being curated
        """
        # skip SCAN files, currently have no derived variables/baseline
        if scope.startswith("scan"):
            log.info(f"Skipping SCAN file")
            return

        if subject.label not in self.__baseline:
            log.warning(f"Subject {subject.label} not found in baseline, skipping")
            return

        # if the file has no derived variables (that start with NACC)
        # nothing to compare, skip
        derived_vars = table.get('file.info.derived')
        if (not derived_vars
            or not any(x.lower().startswith('nacc') for x in derived_vars.keys())):
            log.info("No NACC derived variables, skipping")
            return

        # each subject in the baseline is mapped to a list of ordered records;
        # for UDS need to map the correct record based on visitdate
        # otherwise just grab the most recent record, which should have all the
        # most-updated propogated NACC derived variables
        record = None
        if scope == 'uds':
            for r in self.__baseline[subject.label]:
                if table['file.info.forms.json.visitdate'] == r['visitdate']:
                    record = r
                    break
        else:
            record = self.__baseline[subject.label][-1]

        if not record:
            raise ValueError(f"Could not find matching record for {file_entry.name} "
                             + "in baseline file")

        # make all lowercase in record
        record = {k.lower(): v for k, v in record.items()}

        # finally compare
        failures = []
        for field, value in derived_vars.items():
            field = field.lower()
            if not field.startswith('nacc'):
                continue

            # compare as strings for simplicity
            if str(value) != str(record[field]):
                self.__error_writer.write(
                    unexpected_value_error(field=field,
                                           value=str(value),
                                           expected=str(record[field])))
