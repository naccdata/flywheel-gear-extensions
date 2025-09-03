import logging
from multiprocessing import Manager
from multiprocessing.managers import DictProxy
from typing import Any, Dict, List

from flywheel.models.file_entry import FileEntry
from flywheel.models.subject import Subject
from nacc_attribute_deriver.attribute_deriver import AttributeDeriver
from nacc_attribute_deriver.schema.errors import (
    AttributeDeriverError,
    MissingRequiredError,
)
from nacc_attribute_deriver.symbol_table import SymbolTable
from nacc_attribute_deriver.utils.scope import FormScope, ScopeLiterals
from utils.decorators import api_retry

from .curator import Curator
from .scheduling_models import FileModel

log = logging.getLogger(__name__)


class FormCurator(Curator):
    """Curator that uses NACC Attribute Deriver."""

    def __init__(
        self, deriver: AttributeDeriver, curation_tag: str, force_curate: bool = False
    ) -> None:
        super().__init__(curation_tag=curation_tag, force_curate=force_curate)
        self.__deriver = deriver
        self.__failed_files = Manager().dict()

        # get expected cross-sectional derived variables by scope
        self.__scoped_variables = {
            FormScope.NP: self.__extract_attributes(FormScope.NP),
            FormScope.UDS: self.__extract_attributes(FormScope.UDS),
        }

    def __extract_attributes(self, scope: str) -> List[str]:
        """Extracts the attributes for the given scope.

        Args:
            scope: the scope to extract rules for
        Returns:
            List of attributes (locations)
        """
        curation_rules = self.__deriver.get_curation_rules(scope)
        if not curation_rules:
            raise AttributeDeriverError(
                f"Cannot find any curation rules for scope: {scope}"
            )

        attributes = []
        for rule in curation_rules:
            for assignment in rule.assignments:
                attributes.append(assignment.attribute)

        # in this context we only care about those at
        # subject.info.derived.cross-sectional,
        # so parse out and strip down to the derived variable name
        parent_location = "subject.info.derived.cross-sectional."
        return [
            x.replace(parent_location, "")
            for x in attributes
            if x.startswith(parent_location)
        ]

    @property
    def failed_files(self) -> DictProxy:
        return self.__failed_files

    def get_table(
        self, subject: Subject, subject_table: SymbolTable, file_entry: FileEntry
    ) -> SymbolTable:
        """Returns the SymbolTable with all relevant information for
        curation."""
        # clear out file.info.derived if forcing curation
        if self.force_curate:
            for field in ["derived"]:
                file_entry.delete_info(field)

        return super().get_table(subject, subject_table, file_entry)

    @api_retry
    def apply_file_curation(self, file_entry: FileEntry, table: SymbolTable) -> None:
        """Applies the file-specific curated information back to FW.

        Grabs file.info.derived and copies it back up to the file.
        """
        derived_file_info = table.get("file.info.derived")
        if derived_file_info:
            file_entry.update_info({"derived": derived_file_info})

        if self.curation_tag not in file_entry.tags:
            file_entry.add_tag(self.curation_tag)

    def execute(
        self,
        subject: Subject,
        file_entry: FileEntry,
        table: SymbolTable,
        scope: ScopeLiterals,
    ) -> None:
        """Perform contents of curation. Keeps track of files that failed to be
        curated.

        Args:
            subject: Subject the file belongs to
            file_entry: FileEntry of file being curated
            table: SymbolTable containing file/subject metadata.
            scope: The scope of the file being curated
        """
        try:
            self.__deriver.curate(table, scope)
        except (AttributeDeriverError, MissingRequiredError) as e:
            self.__failed_files[file_entry.name] = str(e)
            log.error(f"Failed to derive {file_entry.name}: {e}")
            return

        # subject data will be applied after all files processed
        # (post-processing step)
        self.apply_file_curation(file_entry, table)

    @api_retry
    def pre_process(self, subject: Subject, subject_table: SymbolTable) -> None:
        """Run pre-processing on the entire subject. Clean up metadata as
        needed.

        Args:
            subject: Subject to pre-process
            subject_table: SymbolTable containing subject-specific metadata
        """
        # if forcing new curation, wipe the subject metadata
        # related to curation.
        if self.force_curate:
            log.debug(
                f"Force curation set to True, cleaning up {subject.label} metadata"
            )
            for field in [
                "cognitive.uds",
                "demographics.uds",
                "derived",
                "genetics",
                "longitudinal-data.uds",
                "neuropathology",
                "study-parameters.uds",
                "working",
            ]:
                subject_table.pop(field)

    @api_retry
    def post_process(  # noqa: C901
        self,
        subject: Subject,
        subject_table: SymbolTable,
        processed_files: List[FileModel],
    ) -> None:
        """Run post-processing on the entire subject.

        1. Pushes final subject_table back to FW
        2. Adds `affiliated` tag to affiliate subjects if
            subject.info.derived.affiliate is set
            (via nacc-attribute-deriver)
        3. Run a second pass over all NP/UDS forms and apply
            cross-sectional values.

        Args:
            subject: Subject to post-process
            subject_table: SymbolTable containing subject-specific metadata
                and curation results
            processed_files: List of FileModels that were processed
        """
        # push subject metadata; need to replace due to potentially
        # cleaned-up metadata
        if subject_table:
            subject.replace_info(subject_table.to_dict())  # type: ignore

        derived = subject_table.get("derived", {})
        affiliate = derived.get("affiliate", None)
        cs_derived = derived.get("cross-sectional", None)

        # add affiliated tag
        if affiliate and "affiliated" not in subject.tags:
            log.debug(f"Tagging affiliate: {subject.label}")
            subject.add_tag("affiliated")

        if not cs_derived:
            log.debug(
                f"No cross-sectional derived variables to back-propogate for {subject.label}"
            )
            return

        # filter out to the scopes
        scope_derived: Dict[str, Dict[str, Any]] = {FormScope.UDS: {}, FormScope.NP: {}}

        for k, v in cs_derived.items():
            for scope in [FormScope.UDS, FormScope.NP]:
                if k in self.__scoped_variables[scope]:
                    scope_derived[scope][k] = v

        log.debug(f"Back-propagating cross-sectional variables for {subject.label}")
        for file in processed_files:
            scope = None
            if file.filename.endswith("_UDS.json"):
                scope = FormScope.UDS
            elif file.filename.endswith("_NP.json"):
                scope = FormScope.NP

            # ignore non-NP/UDS files
            if not scope:
                continue

            file_entry = self.sdk_client.get_file(file.file_id)
            file_entry = file_entry.reload()

            derived = file_entry.info.get("derived", {})
            derived.update(scope_derived[scope])
            file_entry.update_info({"derived": derived})
