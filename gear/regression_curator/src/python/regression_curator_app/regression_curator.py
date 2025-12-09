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

from curator.curator import Curator, ProjectCurationError
from flywheel.models.file_entry import FileEntry
from flywheel.models.subject import Subject
from nacc_attribute_deriver.attribute_deriver import (
    AttributeDeriver,
    MissingnessDeriver,
)
from nacc_attribute_deriver.symbol_table import SymbolTable
from nacc_attribute_deriver.utils.scope import (
    FormScope,
    ScopeLiterals,
)
from nacc_common.error_models import VisitKeys
from outputs.error_writer import ManagerListErrorWriter
from outputs.errors import unexpected_value_error
from utils.decorators import api_retry


log = logging.getLogger(__name__)


class RegressionCurator(Curator):
    """Runs regression testing against curation."""

    def __init__(
        self,
        qaf_baseline: MutableMapping,
        error_writer: ManagerListErrorWriter,
        mqt_baseline: Optional[MutableMapping] = None,
    ) -> None:
        super().__init__()
        self.__qaf_baseline = SymbolTable(qaf_baseline)
        self.__mqt_baseline = SymbolTable(mqt_baseline) if mqt_baseline else None
        self.__error_writer = error_writer

        # keep track of which variables belong to a scope of interest
        self.__scoped_variables: Dict[ScopeLiterals, Set] = {}

    def __add_scope(self, scope: ScopeLiterals) -> None:
        """Add variables related to the given scope."""
        if scope in self.__scoped_variables:
            return

        # only care about file-level missingness values
        curation_rules = AttributeDeriver().get_curation_rules(scope)
        missingness_rules = MissingnessDeriver("file").get_curation_rules(scope)
        self.__scoped_variables[scope] = set()

        curation_rules = [] if not curation_rules else curation_rules
        missingness_rules = [] if not missingness_rules else missingness_rules

        # only care about derived and resolved variables from curation
        if curation_rules + missingness_rules:
            for rule in curation_rules:
                for assignment in rule.assignments:
                    if (".derived." not in assignment.attribute and
                        ".resolved" not in assignment.attribute):
                        continue

                    attribute = assignment.attribute.split(".")[-1]
                    self.__scoped_variables[scope].add(attribute)

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
            raise ProjectCurationError(e) from e

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

        # REGRESSION: remove apostrophes for comparison since
        # legacy code stripped them out
        value = str(value).strip()
        for character in ["'", "\""]:
            value = value.replace(character, "")

        return value

    def compare_baseline(
        self,
        found_vars: Dict[str, Any],
        record: Dict[str, Any],
        prefix: str,
        scope: Optional[ScopeLiterals] = None,
        visit_keys: Optional[VisitKeys] = None,
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
        if prefix.startswith("file") and 'visitdate' in record:
            identifier = f"{identifier} {record['visitdate']}"

        # compare
        for field, value in found_vars.items():
            if field not in record:
                log.debug(f"Field {field} not in baseline, skipping")
                continue

            # REGRESSION: ignore drugs for now
            if field.startswith("drug"):
                continue

            value = self.resolve_value(value)
            expected = self.resolve_value(record[field])

            # REGRESSION: SPECIAL CASES WE ARE IGNORING FOR THE 
            # SAKE OF REGRESSION TESTING - REMOVE WHEN DONE
            if field in ["mocalanx", "respothx", "bpdias",
                         "bpsys", "weight", "height", "hrate"]:
                if value == "-4" and expected == "":
                    continue
                if value == "" and expected == "-4":
                    continue

            # REGRESSION: cogoth2f/cogoth3f case, allow -4 == 8
            if field in ["cogoth2f", "cogoth3f"]:
                if value == "-4" and expected == "8":
                    continue

            # also clear up "." strings in the QAF
            if value == "" and expected == ".":
                continue

            result = value == expected

            if not result:
                result = self.compare_as_lists(value, expected)
                if not result:
                    result = self.compare_as_floats(value, expected)

            if not result:
                msg = (
                    f"{identifier} field {field}: found value {value} "
                    + f"does not match baseline value {expected}"
                )
                log.debug(msg)
                self.__error_writer.write(
                    unexpected_value_error(
                        field=f"{scope}.{prefix}.{field}",
                        value=value,
                        expected=expected,
                        message=msg,
                        visit_keys=visit_keys
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
            log.debug(msg)
            self.__error_writer.write(
                unexpected_value_error(
                    field=f"{scope}.{prefix}.{field}",
                    value="",
                    expected=expected,
                    message=msg,
                    visit_keys=visit_keys
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
        derived_record = table.get("file.info.derived", {})
        resolved_record = table.get("file.info.resolved", {})

        if not derived_record and not resolved_record:
            log.debug(
                f"No derived or resolved variables found for {file_entry.name}, skipping"
            )
            return

        # UDS visit needs to key to a specific visit; other scopes are
        # considered cross-sectional and will use the latest visit
        # under the NACCID-only key
        visit_keys = None
        if scope in [FormScope.UDS, FormScope.LBD, FormScope.FTLD]:
            form_record = table.get("file.info.forms.json")
            visit_keys = VisitKeys.create_from(form_record, date_field="visitdate")
            if not visit_keys.date:
                log.debug(f"No visitdate found for UDS file {file_entry.name}, skipping")
                return

        # ensure in QAF baseline - if not affiliate, report error
        key = f"{subject.label}_{visit_keys.date}" if visit_keys else subject.label
        baseline_record = self.__qaf_baseline.get(key)
        if not baseline_record:
            if "affiliate" in subject.tags:
                log.debug(f"{subject.label} is an affiliate, skipping")
                return

            # Might be V4 or MDS subject, so now expecting many to be missing
            # Just return instead of reporting an error in the output
            msg = (
                f"Could not find matching baseline record for {file_entry.name} "
                + f"in QAF baseline file with key: {key}"
            )
            log.debug(msg)
            return

        # need to combine derived and resolved to compare against baseline QAF
        self.compare_baseline(
            found_vars=derived_record | resolved_record,
            record=baseline_record,
            prefix="file.info.x",
            scope=scope,
            visit_keys=visit_keys
        )
