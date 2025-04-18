import logging

from flywheel import Client
from flywheel.models.file_entry import FileEntry
from flywheel.models.subject import Subject
<<<<<<< HEAD
from nacc_attribute_deriver.attribute_deriver import AttributeDeriver
=======
from flywheel.rest import ApiException
from keys.keys import GearTags
from nacc_attribute_deriver.attribute_deriver import AttributeDeriver, ScopeLiterals
>>>>>>> main
from nacc_attribute_deriver.symbol_table import SymbolTable
from nacc_attribute_deriver.utils.scope import ScopeLiterals

from .curator import Curator

log = logging.getLogger(__name__)


class FormCurator(Curator):
    """Curator that uses NACC Attribute Deriver."""

    def __init__(self,
                 sdk_client: Client,
                 deriver: AttributeDeriver,
                 force_curate: bool = False) -> None:
        super().__init__(sdk_client)
        self.__sdk_client = sdk_client
        self.__deriver = deriver
        self.__force_curate = force_curate

    def apply_curation(self, subject: Subject, file_entry: FileEntry,
                       table: SymbolTable) -> None:
        """Applies the curated information back to FW.

        In its most basic form, grabs file.info.derived subject.info and
        copies it back up to the file/subject. Subclasses that may need
        to apply additional data should override as needed.
        """
        derived_file_info = table.get('file.info.derived')
        subject_info = table.get('subject.info')

        if derived_file_info:
            file_entry.update_info({'derived': derived_file_info})
        if subject_info:
            subject.update_info(subject_info)

    def execute(self, subject: Subject, file_entry: FileEntry,
                table: SymbolTable, scope: ScopeLiterals) -> None:
        """Perform contents of curation.

        Args:
            subject: Subject the file belongs to
            file_entry: FileEntry of file being curated
            table: SymbolTable containing file/subject metadata.
            scope: The scope of the file being curated
        """
        self.__deriver.curate(table, scope)
        self.apply_curation(subject, file_entry, table)
