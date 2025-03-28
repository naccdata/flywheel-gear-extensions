import logging

from flywheel import Client
from flywheel.models.file_entry import FileEntry
from flywheel.models.subject import Subject
from nacc_attribute_deriver.attribute_deriver import AttributeDeriver
from nacc_attribute_deriver.symbol_table import SymbolTable

log = logging.getLogger(__name__)


class FormCurator:
    """Curator that uses NACC Attribute Deriver."""

    def __init__(self, sdk_client: Client, deriver: AttributeDeriver) -> None:
        self.__sdk_client = sdk_client
        self.__deriver = deriver

    @property
    def client(self):
        return self.__sdk_client

    def get_subject(self, file_entry: FileEntry) -> Subject:
        """Get the subject for the file entry.

        Args:
          file_entry: the file entry
        Returns:
          the Subject for the file entry
        """
        parents_subject = file_entry.parents.get("subject")
        return self.client.get_subject(parents_subject)

    def get_table(self, subject: Subject,
                  file_entry: FileEntry) -> SymbolTable:
        """Returns the SymbolTable with all relevant information for curation.

        In it's most basic form, just grabs file.info and subject.info;
        more specific subclasses should grab additional information as
        needed (e.g. for UDS also needs to grab a corresponding NP
        form.)
        """
        # need to reload since info isn't automatically loaded
        subject = subject.reload()
        file_entry = file_entry.reload()

        # add the metadata
        table = SymbolTable({})
        table['subject.info'] = subject.info
        table['file.info'] = file_entry.info
        return table

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

    def curate_file(self, file_id: str):
        """Curate the given file.

        Args:
            file_id: File ID curate
        """

        log.info('curating file %s', file_id)
        file_entry = self.__sdk_client.get_file(file_id)

        subject = self.get_subject(file_entry)
        table = self.get_table(subject, file_entry)

        self.__deriver.curate(table)
        self.apply_curation(subject, file_entry, table)
