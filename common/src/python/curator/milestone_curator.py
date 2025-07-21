"""Defines utilities for Milestone forms."""

from files.milestone_form import MilestoneForm
from flywheel.models.file_entry import FileEntry

from curator.form_curator import FormCurator, curate_session_timestamp


class MilestoneCurator(FormCurator):
    """File curation class for milestone forms."""

    def curate_form(self, file_entry: FileEntry):
        """Curates metadata for milestone form.

        Args:
          file_entry: file entry for form file
        """
        milestone_form = MilestoneForm(file_entry)
        session = self.get_session(file_entry)
        curate_session_timestamp(session, milestone_form)
