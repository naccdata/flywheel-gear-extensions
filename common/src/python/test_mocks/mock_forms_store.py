"""
Mocks datastore.forms_store.FormStore
"""
from datastore.forms_store import FormsStore
from test_mocks.mock_flywheel import MockProject
from typing import Dict, List, Optional


class MockFormsStore(FormsStore):
    """Mocked class of the FormsStore to simulate querying form data
    without actually querying to Flywheel. Basically overrides all
    query functionality to instead return something local."""

    def __init__(self, date_field: str):
        # make fake/nonsense projects, the methods
        # won't be called anyways
        project = MockProject()
        super().__init__(project, project)

        self.__date_field = date_field

        # maps subject to dummy form data
        self.__subjects = {}

        # map files to dummy form data
        self.__files = {}

    def add_subject(self,
                    subject_lbl: str,
                    form_data: Dict[str, str],
                    file_name: str):
        """Add a local "subject"""
        if subject_lbl not in self.__subjects:
            self.__subjects[subject_lbl] = []

        # dummy default visit date
        if self.__date_field not in form_data:
            form_data[self.__date_field] = '2025-01-01'

        self.__subjects[subject_lbl].append(form_data)
        self.__files[file_name] = form_data

    def is_new_subjects(self, subject_lbl: str) -> bool:
        return subject_lbl in self.__subjects

    def query_form_data(
        self,
        subject_lbl: str,
        **kwargs) -> Optional[List[Dict[str, str]]]:
        # TODO - mock rest of query for better testing
        return sorted(self.__subjects[subject_lbl],
                      key=lambda x: x[self.__date_field], reverse=True)

    def query_form_data_with_custom_filters(
        self,
        subject_lbl: str,
        **kwargs) -> Optional[List[Dict[str, str]]]:

        if subject_lbl not in self.__subjects:
            return None

        return sorted(self.__subjects[subject_lbl],
                      key=lambda x: x[self.__date_field], reverse=True)

    def get_visit_data(self, *,
                       file_name: str,
                       acq_id: str) -> Optional[Dict[str, str]]:
        return self.__files[file_name]
