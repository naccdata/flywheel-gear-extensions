from datetime import datetime
from typing import Any, Dict, List, Optional

from flywheel import Session
from flywheel.file_spec import FileSpec
from flywheel.finder import Finder
from flywheel.models.file_entry import FileEntry
from flywheel.models.subject_parents import SubjectParents


class Subject:

    @property
    def id(self) -> str:
        ...

    @property
    def label(self) -> str:
        ...

    # info is "defined" as object
    @property
    def info(self) -> Dict[str, Any]:
        ...

    @property
    def tags(self) -> List[str]:
        ...

    @property
    def type(self) -> str:
        ...

    @property
    def sessions(self) -> Finder[Session]:
        ...

    @property
    def parents(self) -> SubjectParents:
        ...

    def update(
            self,
            *,
            firstname: Optional[str] = None,
            lastname: Optional[str] = None,
            sex: Optional[str] = None,
            cohort: Optional[
                str] = None,  # Cohort is an enum with string value
            race: Optional[str] = None,
            ethnicity: Optional[str] = None,
            date_of_birth: Optional[datetime] = None,
            info: Optional[object] = None,
            type: Optional[str] = None):
        ...

    def add_session(self, label: str) -> Session:
        ...

    def reload(self) -> Subject:
        ...

    def update_info(self, *args, **kwargs):
        """Update the info with the passed in arguments."""
        ...

    def get_file(self, name: str) -> FileEntry:
        ...

    def upload_file(self, file: FileSpec) -> List[Dict]:
        ...

    def delete_info(self, *args, **kwargs):
        ...

    def add_tag(self, tag, **kwargs):
        ...

    def delete_tag(self, tag, **kwargs):
        ...
