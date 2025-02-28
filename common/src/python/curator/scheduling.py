import multiprocessing
import os
from datetime import date
from multiprocessing import Pool
from typing import Dict, List, Type, TypeVar

from dataview.dataview import ColumnModel, make_builder
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from flywheel_gear_toolkit.context.context import GearToolkitContext
from pydantic import BaseModel, ValidationError
from scheduling.min_heap import MinHeap

from curator.form_curator import FormCurator

C = TypeVar('C', bound=FormCurator)


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
    """Defines the data model for a dataview response."""
    data: List[FileModel]


class ProjectFormCurator:
    """Defines a curator for applying a FormCurator to the files in a project.
    """

    def __init__(self, proxy: FlywheelProxy,
                 heap_map: Dict[str, MinHeap[FileModel]]) -> None:
        self.__proxy = proxy
        self.__heap_map = heap_map

    @classmethod
    def create(cls, project: ProjectAdaptor) -> 'ProjectFormCurator':
        """Creates a ProjectFormCurator for the projects.
        
        Pulls information for all of the files in the project.
        
        Args:
          project: the project
        Returns:
          the ProjectFormCurator for the form files in the project
        """
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
            filter_str='file.classification.type=|[UDS]')
            # filter_str='file.classification.type=|[UDS,LBD,FTLD]')
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

    def __compute_cores(self) -> int:
        """Attempts to compute the number of cores available for processes.

        Apparently, sometimes multiprocessing.cpu_count() returns the
        number of active cores as opposed to the actual cores. Stack
        Overflow claims the solution on Linux is to query the process,
        which needs to pid. So, just asking the os, and multiprocessing.
        """
        os_cpu_count = os.cpu_count()
        os_cpu_cores: int = os_cpu_count if os_cpu_count else 1
        return max(1, max(os_cpu_cores - 1, multiprocessing.cpu_count() - 1))

    def apply(self, curator_type: Type[C],
              context: GearToolkitContext) -> None:
        """Applies a FormCurator to the form files in this curator.

        Builds a curator of the type given with the context to avoid shared
        state across curators.

        Args:
          curator_type: a FormCurator subclass
          context: the gear context
        """

        def curate_subject(heap: MinHeap[FileModel]) -> None:
            """Defines a task function for curating the files captured in the
            heap. 

            Uses the context of the outer apply method to create the curator.
            
            Assumes the files are all under the sample user.
            
            Args:
              heap: the min heap of file model objects
            """
            while len(heap) > 0:
                file_info = heap.pop()
                if not file_info:
                    continue
                file_entry = self.__proxy.get_file(file_info.file_id)
                curator = curator_type(context=context)
                curator.curate_container(file_entry)

        process_count = max(4, self.__compute_cores())
        with Pool(processes=process_count) as pool:
            for heap in self.__heap_map.values():
                pool.apply_async(curate_subject, (heap, ))
            pool.close()
            pool.join()


class ProjectCurationError(Exception):
    """Exception for errors curating project files."""
