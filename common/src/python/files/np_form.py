"""Defines form class for NPv11 forms."""

from datetime import datetime
from typing import Optional

from dates.dates import datetime_from_form_date

from files.form import Form


class NPv11Form(Form):
    """NPv11 form class used for attribute curation."""

    def get_session_date(self) -> Optional[datetime]:
        """Get date of NP session.

        Args:
        file_o: the NP file entry
        Returns:
        the date time value for the NP visit, None if not found
        """
        visit_datetime = None
        visit_date = self.get_metadata("formdate_np")
        if visit_date:
            visit_datetime = datetime_from_form_date(visit_date)
        return visit_datetime
