"""Regression curator. Similar to the form curator, but runs a regression test
against the files instead of curating them. Assumes files have already been
curated.

Baseline is a dict mapping each NACCID to a list of dicts containing the
QAF derived values for a given form/visit (e.g. any fields that start
with NACC or key values such as as visit date.)
"""

import ast  # type: ignore
import math
import logging
from typing import Any, Dict, MutableMapping, Optional, Set

from flywheel.models.file_entry import FileEntry
from flywheel.models.subject import Subject
from nacc_attribute_deriver.attribute_deriver import (
    AttributeDeriver,
    MissingnessDeriver,
)
from nacc_attribute_deriver.symbol_table import SymbolTable
from nacc_attribute_deriver.utils.scope import ScopeLiterals
from outputs.error_writer import ManagerListErrorWriter
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
        error_writer: ManagerListErrorWriter,
        max_errors: int,
        mqt_baseline: Optional[MutableMapping] = None,
    ) -> None:
        super().__init__()
        self.__qaf_baseline = SymbolTable(qaf_baseline)
        self.__mqt_baseline = SymbolTable(mqt_baseline) if mqt_baseline else None
        self.__error_writer = error_writer
        self.__max_errors = max_errors

        # keep track of which variables belong to a scope of interest
        self.__scoped_variables: Dict[ScopeLiterals, Set] = {}

    def __add_scope(self, scope: ScopeLiterals) -> None:
        """Add variables related to the given scope."""
        if scope in self.__scoped_variables:
            return

        curation_rules = AttributeDeriver().get_curation_rules(scope)
        missingness_rules = MissingnessDeriver().get_curation_rules(scope)

        self.__scoped_variables[scope] = set()
        for rule in curation_rules + missingness_rules:
            for assignment in rule.assignments:
                # for now, only care about derived and resolved variables
                if (".derived." not in assignment.attribute and
                    ".resolved." not in assignment.attribute):
                    continue

                attribute = assignment.attribute.split(".")[-1]
                self.__scoped_variables[scope].add(attribute)

    def break_curation(self) -> bool:
        """Used to globally signal to scheduler that curation should stop."""
        return len(self.__error_writer.errors()) >= self.__max_errors

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
        try:
            return set(value_as_list) == set(expected_as_list)
        except TypeError as e:
            # means dicts - we assume lists of dicts are ordered, so
            # if it failed the earlier equality test then it doesn't match
            if str(e) == "unhashable type: 'dict'":
                return False

            # otherwise some other issue, so raise error
            raise e

        return False

    def compare_as_floats(self, value: str, expected: str) -> bool:
        """Checks if the values look like floats and may just have different
        formatting, and also check precision.

        Args:
            value: Value to compare
            expected: Expected value to compare
        Returns:
            False if they are not both floats or still do not match
        """
        try:
            # allow within 0.001 precision
            return math.isclose(float(value), float(expected), abs_tol=0.001)
        except (ValueError, TypeError):
            return False

        return False

    def resolve_value(self, value: Any) -> str:
        """Resolve values; change everything to a string for easy
        comparison."""
        # make sure Nones and empty strings are treated the same
        if value is None or str(value).strip() == "":
            return ""

        # convert booleans to 0/1
        if isinstance(value, bool):
            value = int(value)

        return str(value).strip()

    def compare_baseline(
        self,
        found_vars: Dict[str, Any],
        record: Dict[str, Any],
        prefix: str,
        scope: Optional[ScopeLiterals] = None,
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
            scope: The scope; if specified, only focus on the baseline
                variables that exist in the scope
        """
        # make all lowercase for consistency
        found_vars = {k.lower(): v for k, v in found_vars.items()}
        record = {k.lower(): v for k, v in record.items()}

        identifier = record["naccid"]
        if prefix.startswith("file"):
            identifier = f"{identifier} {record['visitdate']}"

        # compare
        for field, value in found_vars.items():
            if field not in record:
                log.debug(f"Field {field} not in baseline, skipping")
                continue

            value = self.resolve_value(value)
            expected = self.resolve_value(record[field])
            result = value == expected

            if field == "adgcexr":
                raise ValueError(f"JDAKLFAKJSLFJDFKLASDLFKJL {result}: {value} vs {expected}")

            if not result:
                result = self.compare_as_lists(value, expected)
                if not result:
                    result = self.compare_as_floats(value, expected)

            if not result:
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

        # report on any variables in record but not in found_vars
        # also ignore variables not in the given scope
        self.__add_scope(scope)
        missing = set(record.keys()) - set(found_vars.keys())
        missing = missing.intersection(self.__scoped_variables[scope])

        for field in missing:
            if field in ["visitdate", "naccid"]:
                continue

            expected = str(record[field]).strip()

            if not expected:
                continue

            msg = (
                f"{identifier} field {field}: baseline {field} with value "
                + f"{expected} not found in curated variables (likely "
                + "returned None)"
            )
            log.info(msg)
            self.__error_writer.write(
                unexpected_value_error(
                    field=f"{prefix}.{field}",
                    value="",
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
        derived_record = table.get("file.info.derived", None)
        resolved_record = table.get("file.info.resolved", None)

        if not derived_record and not resolved_record:
            log.debug(
                f"No derived or resolved variables found for {file_entry.name}, skipping"
            )
            return

        visitdate = table.get("file.info.forms.json.visitdate")
        if not visitdate:
            # try MRI version
            if "file.info.raw.mriyr" in table:
                visitdate = (
                    f"{int(table['file.info.raw.mriyr']):04d}-"
                    + f"{int(table['file.info.raw.mrimo']):02d}-"
                    + f"{int(table['file.info.raw.mridy']):02d}"
                )

        if not visitdate and scope == FormScope.UDS:
            log.debug(f"No visitdate found for UDS file {file_entry.name}, skipping")
            return

        # ensure in QAF baseline - if not affiliate, report error
        key = f"{subject.label}_{visitdate}" if visitdate else subject.label
        baseline_record = self.__qaf_baseline.get(key)
        if not baseline_record:
            if "affiliate" in subject.tags:
                log.debug(f"{subject.label} is an affiliate, skipping")
                return

            msg = (
                f"Could not find matching baseline record for {file_entry.name} "
                + f"in QAF baseline file with key: {key}"
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

        # need to combine derived and resolved to compare against baseline QAF
        self.compare_baseline(
            found_vars=derived_record | resolved_record,
            record=baseline_record,
            prefix="file.info.x",
            scope=scope,
        )

    # This is pretty much only for MQT, which is not relevant at this point

    # @api_retry
    # def pre_curate(self, subject: Subject, subject_info: SymbolTable) -> None:
    #     """Run pre-curating on the entire subject. Compares subject.info.

    #     Args:
    #         subject: Subject to pre-process
    #     """
    #     if not self.__mqt_baseline:
    #         return

    #     if not subject_info:
    #         log.debug("No subject derived variables, skipping")
    #         return

    #     # means subject hasn't been curated before - might not
    #     # be worth reporting in the long run but for now over report,
    #     # can be used as an indicator of new subjects
    #     if subject.label not in self.__mqt_baseline:
    #         msg = f"Could not find curated subject {subject.label} in MQT baseline"
    #         log.warning(msg)

    #         self.__error_writer.write(
    #             unexpected_value_error(
    #                 field="subject.label",
    #                 value=None,  # type: ignore
    #                 expected=subject.label,
    #                 message=msg,
    #             )
    #         )
    #         return

    #     record = self.__mqt_baseline[subject.label]
    #     found_vars = flatten_dict(subject_info.to_dict())

    #     self.compare_baseline(found_vars, record, prefix="subject.info")
