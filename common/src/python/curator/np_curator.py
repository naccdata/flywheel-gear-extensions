"""Curation utilities for NP forms."""

from files.np_form import NPv11Form
from flywheel.models.file_entry import FileEntry

from curator.form_curator import FormCurator, curate_session_timestamp


class NPv11Curator(FormCurator):
    """File curator for NPv11 forms."""

    def curate_form(self, file_entry: FileEntry):
        """Curate metadata for NPv11 form.

        Args:
          file_entry: the file entry for the form
        """
        form = NPv11Form(file_entry)
        session = self.get_session(file_entry)
        curate_session_timestamp(session, form)
