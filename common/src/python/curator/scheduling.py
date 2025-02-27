from datetime import date
from typing import Dict, List, Optional

from dataview.dataview import ColumnModel, make_builder
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from pydantic import BaseModel, ValidationError
from scheduling.min_heap import MinHeap

from curator.form_curator import FormCurator


class FileModel(BaseModel):
    """Defines data model for columns returned from the project form curator
    data model.

    Objects are ordered by visit date.
    """
    filename: str
    file_id: str
    acquisition_id: str
    subject_id: str
    module: str
    visitdate: date

    def __eq__(self, other) -> bool:
        if not isinstance(other, FileModel):
            return False

        return self.file_id == other.file_id

    def __lt__(self, other) -> bool:
        if not isinstance(other, FileModel):
            return False

        if self.module == 'UDS' and other.module != 'UDS':
            return False

        return self.visitdate < other.visitdate


class ViewResponseModel(BaseModel):
    data: List[FileModel]


class ProjectFormCurator:

    def __init__(self, proxy: FlywheelProxy,
                 heap_map: Dict[str, MinHeap[FileModel]]) -> None:
        self.__proxy = proxy
        self.__heap_map = heap_map

    @classmethod
    def create(cls, project: ProjectAdaptor) -> Optional['ProjectFormCurator']:
        builder = make_builder(
            label='form-curation-scheduling',
            description='Lists form files for curation',
            columns=[
                ColumnModel(data_key="file.name", label="filename"),
                ColumnModel(data_key="file.file_id", label="file_id"),
                ColumnModel(data_key="file.parents.acquisition",
                            label="acquisition_id"),
                ColumnModel(data_key="file.parents.subject",
                            label="subject_id"),
                ColumnModel(data_key="file.info.forms.json.module",
                            label="module"),
                ColumnModel(data_key='file.info.forms.json.visitdate',
                            label="visitdate")
            ],
            container='acquisition',
            filename="*.json",
            filter_str='file.classification.type=|[UDS,LBD,FTLD]')
        view = builder.build()

        with project.read_dataview(view) as response:
            response_data = response.read()
            try:
                response_model = ViewResponseModel.model_validate_json(
                    response_data)
            except ValidationError as error:
                raise ProjectCurationError(
                    f'Error curating project {project.label}: {error}'
                ) from error

        subject_heap_map = {}
        for file_info in response_model.data:
            heap = subject_heap_map.get(file_info.subject_id,
                                        MinHeap[FileModel]())
            heap.push(file_info)

        return ProjectFormCurator(proxy=project.proxy,
                                  heap_map=subject_heap_map)

    def apply(self, curator: FormCurator) -> None:
        # iterate over heaps for individual subjects and curate files
        # potential namespace conflicts are at subject level
        for heap in self.__heap_map.values():
            # this could be an independent process
            while len(heap) > 0:
                file_info = heap.pop()
                if not file_info:
                    continue
                file_entry = self.__proxy.get_file(file_info.file_id)
                curator.curate_container(file_entry)


class ProjectCurationError(Exception):
    """Exception for errors curating project files."""
