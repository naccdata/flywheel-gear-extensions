"""Regression curator. Similar to the form curator, but runs a regression test
against the files instead of curating them. Assumes files have already been
curated.

Baseline is a dict mapping each NACCID to a list of dicts containing the
QAF derived values for a given form/visit (e.g. any fields that start
with NACC or key values such as as visit date.)
"""

import ast  # type: ignore
import logging
from typing import Any, Dict, MutableMapping, Optional

from flywheel.models.file_entry import FileEntry
from flywheel.models.subject import Subject
from nacc_attribute_deriver.symbol_table import SymbolTable
from nacc_attribute_deriver.utils.scope import ScopeLiterals
from outputs.error_writer import ErrorWriter
from outputs.errors import unexpected_value_error
from utils.decorators import api_retry
from utils.utils import flatten_dict

from .curator import Curator

log = logging.getLogger(__name__)


class RegressionCurator(Curator):
    """Runs regression testing against curation."""

    def __init__(
        self,
        qaf_baseline: MutableMapping,
        error_writer: ErrorWriter,
        mqt_baseline: Optional[MutableMapping] = None,
    ) -> None:
        super().__init__()
        self.__qaf_baseline = SymbolTable(qaf_baseline)
        self.__mqt_baseline = SymbolTable(mqt_baseline) if mqt_baseline else None
        self.__error_writer = error_writer

    def compare_as_lists(self, value: str, expected: str) -> bool:
        """Checks if the values look like lists; if so, compare as sets to
        ignore ordering.

        Args:
            value: Value to compare
            expected: Expected value to compare
        Returns:
            False if they are not both lists or still do not match
        """
        # check if they look like lists just based on brackets
        if not all(x.startswith("[") and x.endswith("]") for x in [value, expected]):
            return False

        # try to literal_eval as lists, and check they are in fact lists
        expected_as_list = ast.literal_eval(expected)
        value_as_list = ast.literal_eval(value)

        if not all(isinstance(x, list) for x in [value_as_list, expected_as_list]):
            return False

        # compare as sets
        return set(value_as_list) == set(expected_as_list)

    def compare_baseline(
        self, found_vars: Dict[str, Any], record: Dict[str, Any], prefix: str
    ) -> None:
        """Compare derived/curated variables to the baseline. Assumes both
        found_vars and record are flat dicts.

        Always checks found vs record, but not the other way around,
        so will not account for variables that may be missing in the
        found vars.

        Args:
            found_vars: Found variables to compare to baseline
            record: Baseline record to compare to
            prefix: Field prefix
        """
        # make all lowercase for consistency
        found_vars = {k.lower(): v for k, v in found_vars.items()}
        record = {k.lower(): v for k, v in record.items()}

        # compare
        for field, value in found_vars.items():
            if field not in record:
                log.warning(f"Field {field} not in baseline, skipping")
                continue

            # convert booleans to 0/1
            if isinstance(value, bool):
                value = int(value)

            value = str(value)
            expected = str(record[field])
            result = (value == expected) or self.compare_as_lists(value, expected)

            if not result:
                identifier = record["naccid"]
                if prefix.startswith("file"):
                    identifier = f"{identifier} {record['visitdate']}"

                msg = (
                    f"{identifier} field {field}: found value {value} "
                    + f"does not match baseline value {expected}"
                )
                log.info(msg)
                self.__error_writer.write(
                    unexpected_value_error(
                        field=f"{prefix}.{field}",
                        value=value,
                        expected=expected,
                        message=msg,
                    )
                )

    def execute(
        self,
        subject: Subject,
        file_entry: FileEntry,
        table: SymbolTable,
        scope: ScopeLiterals,
    ) -> None:
        """Perform contents of curation. Assumes UDS data.

        Args:
            subject: Subject the file belongs to
            file_entry: FileEntry of file being curated
            table: SymbolTable containing file/subject metadata.
            scope: The scope of the file being curated
        """
        # skip if not UDS, no derived variables, or no visitdate found
        if scope != "uds":
            log.debug(f"{file_entry.name} is a not an UDS form, skipping")
            return

        derived_vars = table.get("file.info.derived", None)
        if not derived_vars or not any(
            x.lower().startswith("nacc") for x in derived_vars
        ):
            log.debug(f"No derived variables found for {file_entry.name}, skipping")
            return

        visitdate = table.get("file.info.forms.json.visitdate")
        if not visitdate:
            log.debug(f"No visitdate found for {file_entry.name}, skipping")
            return

        # ensure in QAF baseline - if not affiliate, report error
        key = f"{subject.label}_{visitdate}"
        record = self.__qaf_baseline.get(key)
        if not record:
            if "affiliate" in subject.tags:
                log.debug(f"{subject.label} is an affiliate, skipping")
                return

            msg = (
                f"Could not find matching record for {file_entry.name} "
                + f"in QAF baseline file with NACCID and visitdate: {key}"
            )
            log.warning(msg)
            self.__error_writer.write(
                unexpected_value_error(
                    field="naccid",
                    value=None,  # type: ignore
                    expected=key,
                    message=msg,
                )
            )
            return

        self.compare_baseline(derived_vars, record, prefix="file.info.derived")

    @api_retry
    def pre_process(self, subject: Subject) -> None:
        """Run pre-processing on the entire subject. Compares subject.info.

        Args:
            subject: Subject to pre-process
        """
        if not self.__mqt_baseline:
            return

        subject = subject.reload()
        if not subject.info:
            log.debug("No subject derived variables, skipping")
            return

        # means subject hasn't been curated before - might not
        # be worth reporting in the long run but for now over report,
        # can be used as an indicator of new subjects
        if subject.label not in self.__mqt_baseline:
            msg = f"Could not find curated subject {subject.label} in MQT baseline"
            log.warning(msg)

            self.__error_writer.write(
                unexpected_value_error(
                    field="subject.label",
                    value=None,  # type: ignore
                    expected=subject.label,
                    message=msg,
                )
            )
            return

        record = self.__mqt_baseline[subject.label]
        found_vars = flatten_dict(subject.info)

        self.compare_baseline(found_vars, record, prefix="subject.info")
