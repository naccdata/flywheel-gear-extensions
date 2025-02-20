from datetime import date
from typing import List, Optional

from dataview.dataview import ColumnModel, make_builder
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_gear_toolkit.utils.curator import FileCurator
from pydantic import BaseModel, ValidationError
from scheduling.min_heap import MinHeap


class FileModel(BaseModel):
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

    def __init__(self, heap: MinHeap[FileModel]) -> None:
        self.__heap = heap

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
            except ValidationError:
                # TODO: throw exception
                return None

        heap = MinHeap[FileModel]()
        for file_info in response_model.data:
            heap.push(file_info)

        return ProjectFormCurator(heap=heap)

    def apply(self, curator: FileCurator) -> None:
        pass
