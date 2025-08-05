"""Mocks datastore.forms_store.FormStore."""

from typing import Dict, List, Optional

from datastore.forms_store import FormsStore
from keys.keys import FieldNames, MetadataKeys

from test_mocks.mock_flywheel import MockProject


class MockFormsStore(FormsStore):
    """Mocked class of the FormsStore to simulate querying form data without
    actually querying to Flywheel.

    Basically overrides all query functionality to instead return
    something local.
    """

    def __init__(self, date_field: str):
        # make fake/nonsense projects, the methods
        # won't be called anyways
        project = MockProject(label="mock-project")
        super().__init__(project, project)

        self.__date_field = date_field

        # maps subject to acquisition to filename to form data
        self.__subjects = {}  # type: ignore

    def add_subject(self, subject_lbl: str, form_data: Dict[str, str], file_name: str):
        """Add a local "subject."""
        if subject_lbl not in self.__subjects:
            self.__subjects[subject_lbl] = {}

        # dummy default visit date
        if self.__date_field not in form_data:
            form_data[self.__date_field] = "2025-01-01"

        module = form_data[FieldNames.MODULE]
        if module not in self.__subjects[subject_lbl]:
            self.__subjects[subject_lbl][module] = {}

        self.__subjects[subject_lbl][module][file_name] = form_data

    def is_new_subject(self, subject_lbl: str) -> bool:
        return subject_lbl not in self.__subjects

    def query_form_data(
        self, subject_lbl: str, module: str, **kwargs
    ) -> Optional[List[Dict[str, str]]]:
        # TODO - mock rest of query for better testing, this
        # is basically hardcoded to return whatever passes the tests
        if subject_lbl not in self.__subjects:
            return None
        module = module.lower()
        if module not in self.__subjects[subject_lbl]:
            return None

        result = []
        date_col_lbl = f"{MetadataKeys.FORM_METADATA_PATH}.{self.__date_field}"
        for file, form_data in self.__subjects[subject_lbl][module].items():
            result.append(
                {
                    "file.name": file,
                    "file.parents.acquisition": module,
                    date_col_lbl: form_data["visitdate"],
                    "file.file_id": "dummy-id",
                }
            )

        return sorted(result, key=lambda x: x[date_col_lbl], reverse=True)

    def query_form_data_with_custom_filters(
        self, **kwargs
    ) -> Optional[List[Dict[str, str]]]:
        return self.query_form_data(**kwargs)

    def get_visit_data(
        self, *, file_name: str, acq_id: str
    ) -> Optional[Dict[str, str]]:
        for modules in self.__subjects.values():
            for module, files in modules.items():
                if module != acq_id:
                    continue
                if file_name in files:
                    return files[file_name]

        return None
