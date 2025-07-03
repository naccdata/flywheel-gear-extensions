import logging
from multiprocessing import Manager
from multiprocessing.managers import DictProxy
from typing import List

from flywheel.models.file_entry import FileEntry
from flywheel.models.subject import Subject
from flywheel.rest import ApiException
from nacc_attribute_deriver.attribute_deriver import AttributeDeriver
from nacc_attribute_deriver.symbol_table import SymbolTable
from nacc_attribute_deriver.utils.scope import ScopeLiterals
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

    @property
    def failed_files(self) -> DictProxy:
        return self.__failed_files

    def get_table(self,
                  subject: Subject,
                  subject_table: SymbolTable,
                  file_entry: FileEntry) -> SymbolTable:
        """Returns the SymbolTable with all relevant information for
        curation."""
        # clear out file.info.derived if forcing curation
        if self.force_curate:
            for field in ["derived"]:
                file_entry.delete_info(field)

        return super().get_table(subject, subject_table, file_entry)

    @api_retry
    def apply_file_curation(
        self, file_entry: FileEntry, table: SymbolTable
    ) -> None:
        """Applies the file-specific curated information back to FW 

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
        except Exception as e:
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
                "working"
            ]:
                subject_table.pop(field)

    @api_retry
    def post_process(self,
                     subject: Subject,
                     subject_table: SymbolTable,
                     processed_files: List[FileModel]) -> None:
        """Run post-processing on the entire subject.

        1. Adds `affiliated` tag to affiliate subjects if
            subject.info.derived.affiliate is set
            (via nacc-attribute-deriver)
        2. Run a second pass over all UDS forms and apply
            cross-sectional values.
        3. Pushes final subject_table back to FW

        Args:
            subject: Subject to post-process
            subject_table: SymbolTable containing subject-specific metadata
                and curation results
            processed_files: List of FileModels that were processed
        """
        derived = subject_table.get("derived", {})
        affiliate = derived.get("affiliate", None)
        cs_derived = derived.get("cross-sectional", None)

        # add affiliated tag
        if affiliate and "affiliated" not in subject.tags:
            log.debug(f"Tagging affiliate: {subject.label}")
            subject.add_tag("affiliated")

        if not cs_derived:
            return

        log.debug(f"Back-propagating cross-sectional UDS variables for {subject.label}")
        for file in processed_files:
            # ignore non-UDS files
            if not file.filename.endswith("_UDS.json"):
                continue

            file_entry = self.sdk_client.get_file(file.file_id)
            file_entry = file_entry.reload()

            derived = file_entry.info.get("derived", {})
            derived.update(cs_derived)
            file_entry.update_info({"derived": derived})

        # push subject metadata
        if subject_table:
            subject.update_info(subject_table.to_dict())
