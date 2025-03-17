import logging
from abc import abstractmethod
from typing import Any, Dict, Optional

from dates.dates import get_localized_timestamp
from files.form import Form
from flywheel.models.acquisition import Acquisition
from flywheel.models.file_entry import FileEntry
from flywheel.models.session import Session
from flywheel.models.subject import Subject
from flywheel_gear_toolkit.context.context import GearToolkitContext
from flywheel_gear_toolkit.utils.curator import Curator

log = logging.getLogger(__name__)


class FormCurator:
    """Curator that uses NACC Attribute Deriver."""

    def __init__(self,
                 context: GearToolKitContext,
                 deriver: NACCAttributeDeriver) -> None:
        self.__context = context
        self.__deriver = deriver

    def get_subject(self, file_entry: FileEntry) -> Subject:
        """Get the subject for the file entry.

        Args:
          file_entry: the file entry
        Returns:
          the Subject for the file entry
        """
        parents_subject = file_entry.parents.get("subject")
        return self.__context.client.get_subject(parents_subject)

    def get_table(self, subject: Subject, file_entry: FileEntry) -> SymbolTable:
        """Returns the SymbolTable with all relevant information for curation.

        In it's most basic form, just grabs file.info and subject.info;
        more specific subclasses should grab additional information as
        needed (e.g. for UDS also needs to grab a corresponding NP form.)
        """
        # need to reload since info isn't automatically loaded
        subject = subject.reload()
        file_entry = file_entry.reload()

        # add the metadata
        table = SymbolTable()
        table.update(subject.info)
        table.update(file_entry.info)
        return table

    def apply_curation(self, subject: Subject, table: SymbolTable) -> None:
        """Applies the curated information back to FW.

        In its most basic form, grabs subject.info and copies it back up
        to the subject. Subclasses that may need to apply additional data
        should override as needed.
        """
        subject.update(info=table.get('subject.info', {}))

    def curate_container(self, file_entry: FileEntry):
        """Curate the given container.

        Args:
            file_entry: File to curate
        """
        log.info('curating container %s', file_entry.id)
        subject = self.get_subject(file_entry)
        table = self.get_table(subject, file_entry)

        self.__deriver.curate(table)
        self.apply_curation(subject, table)
