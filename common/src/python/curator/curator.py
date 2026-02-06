"""Defines a base abstract curator for scheduling."""

import logging
from abc import ABC, abstractmethod
from codecs import StreamReader
from multiprocessing import Manager
from multiprocessing.managers import ListProxy
from typing import List, Optional

from flywheel import Client, DataView
from flywheel.models.subject import Subject
from fw_gear import GearContext
from nacc_attribute_deriver.symbol_table import SymbolTable
from nacc_attribute_deriver.utils.scope import ScopeLiterals
from utils.decorators import api_retry

from .scheduling_models import FileModel

log = logging.getLogger(__name__)


class ProjectCurationError(Exception):
    pass


class Curator(ABC):
    """Base curator abstract class."""

    def __init__(
        self,
        dataview: DataView,
        curation_tag: Optional[str] = None,
        force_curate: bool = False,
    ) -> None:
        self.__dataview = dataview
        self.__curation_tag = curation_tag
        self.__force_curate = force_curate
        self.__sdk_client: Client | None = None

        self.__failed_files = Manager().list()

    @property
    def sdk_client(self) -> Client:
        if not self.__sdk_client:
            raise ProjectCurationError("SDK Client not set")

        return self.__sdk_client

    @property
    def curation_tag(self) -> Optional[str]:
        return self.__curation_tag

    @property
    def force_curate(self) -> bool:
        return self.__force_curate

    @property
    def failed_files(self) -> ListProxy:
        return self.__failed_files

    def set_client(self, context: GearContext) -> None:
        """Set the SDK client. For multiprocessing, this client must be
        separate per process, so expected to be set at the worker instantiation
        level.

        Args:
            context: Context to set client from
        """
        self.__sdk_client = context.get_client()

    def add_curation_failure(self, container: Subject | FileModel, reason: str) -> None:
        """Creates a curation failure dict from either a Subject or FileModel.

        Needs to be picklelable.
        """
        if isinstance(container, FileModel):
            error = {
                "name": container.filename,
                "id": container.file_id,
                "reason": reason,
            }
        else:
            error = {"name": container.label, "id": container.id, "reason": reason}  # type: ignore

        self.__failed_files.append(error)

    @api_retry
    def read_dataview(self, subject_id: str) -> StreamReader:
        """Read the dataview on the given subject."""
        return self.sdk_client.read_view_data(self.__dataview, subject_id)

    @api_retry
    def get_subject(self, subject_id: str) -> Subject:
        """Get the subject for the given subject ID.

        Args:
          subject_id: the subject ID
        Returns:
          the corresponding Subject
        """
        return self.sdk_client.get_subject(subject_id)

    @api_retry
    def get_table(
        self, subject: Subject, subject_table: SymbolTable, file_model: FileModel
    ) -> SymbolTable:
        """Returns the SymbolTable with all relevant information for curation.

        Args:
            subject: The subject the file belongs to
            subject_table: SymbolTable containing subject-specific metadata
                to curate to. Iteratively added onto for each file curation
            file_entry: The file being curated
        """
        # add the metadata
        table = SymbolTable({})

        # SymbolTable.to_dict() returns the internal dict object; this same object
        # is passed to each file's iteration of this table, so in practice is
        # mutated globally
        table["subject.info"] = subject_table.to_dict()
        table["file.info"] = file_model.file_info

        return table

    @api_retry
    def curate_file(
        self, subject: Subject, subject_table: SymbolTable, file_model: FileModel
    ) -> bool:
        """Curates a file.

        Args:
            subject: Subject the file belongs to
            subject_table: SymbolTable containing subject-specific metadata
                to curate to. Iteratively added onto for each file curation
            file_model: the file model to curate

        Returns:
            True if successfully curated (or skipped), False if there was some
                failure while curating
        """
        if (
            self.curation_tag
            and not self.force_curate
            and self.curation_tag in file_model.file_tags
        ):
            log.debug(f"{file_model.filename} already curated, skipping")
            return True

        scope = file_model.scope
        if not scope:
            log.warning(
                "could not determine scope for %s, skipping", file_model.filename
            )
            return True

        table = self.get_table(subject, subject_table, file_model)
        log.debug("curating file %s with scope %s", file_model.filename, scope)
        return self.execute(subject, file_model, table, scope)

    def pre_curate(self, subject: Subject, subject_table: SymbolTable) -> None:
        """Run pre-curation on the entire subject. Not required.

        Args:
            subject: Subject to pre-process
            subject_table: SymbolTable containing subject-specific metadata
        """
        return

    def post_curate(
        self,
        subject: Subject,
        subject_table: SymbolTable,
        processed_files: List[FileModel],
    ) -> None:
        """Run post-curation on the entire subject. Not required.

        Args:
            subject: Subject to post-process
            subject_table: SymbolTable containing subject-specific metadata
                and curation results
            processed_files: List of FileModels that were successfully processed
        """
        return

    @abstractmethod
    def execute(
        self,
        subject: Subject,
        file_model: FileModel,
        table: SymbolTable,
        scope: ScopeLiterals,
    ) -> bool:
        """Perform contents of curation.

        Args:
            subject: Subject the file belongs to
            file_model: FileModel of file being curated
            table: SymbolTable containing file/subject metadata.
            scope: The scope of the file being curated
        """
        return True
