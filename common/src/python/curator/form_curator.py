import logging

from flywheel.models.file_entry import FileEntry
from flywheel.models.subject import Subject
from flywheel_gear_toolkit.context.context import GearToolkitContext
from nacc_attribute_deriver.attribute_deriver import NACCAttributeDeriver
from nacc_attribute_deriver.symbol_table import SymbolTable

log = logging.getLogger(__name__)


class FormCurator:
    """Curator that uses NACC Attribute Deriver."""

    def __init__(self, context: GearToolkitContext,
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

    def apply_curation(self,
                       subject: Subject,
                       file_entry: FileEntry,
                       table: SymbolTable) -> None:
        """Applies the curated information back to FW.

        In its most basic form, grabs file.info.derived subject.info and copies
        it back up to the file/subject. Subclasses that may need to apply
        additional data should override as needed.
        """
        file_entry.update(info=table.get('file.info.derived', {}))
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
        self.apply_curation(subject, file_entry, table)


class UDSFormCurator(FormCurator):
    """UDS Form curator - also needs to grab NP."""

    def get_table(self, subject: Subject,
                  file_entry: FileEntry) -> SymbolTable:
        """Get table - also needs to grab NP data."""
        table = super().get_table(subject, file_entry)

        # TODO: easier way to find?
        for session in subject.sessions():  # type: ignore
            if session.label.startswith('NP-'):
                # only one NP form
                acq = session.acquisitions()
                assert len(acq) == 1 and len(acq[0].files) == 1, \
                    f"More than one NP form found for {subject.label}"
                np_form = self.__context.client.get_file(
                    acq[0].files[0].file_id).info
                table['file.info.np'] = np_form['forms']['json']
                return table

        log.warning(f"No NP form found for {subject.label}")
        return table
