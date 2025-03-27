"""Scheduling for project curation."""
import logging
from datetime import date
import multiprocessing
import os
from typing import Dict, List, Type, TypeVar

from dataview.dataview import ColumnModel, make_builder
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_gear_toolkit import GearToolkitContext
from pydantic import BaseModel, ValidationError
from scheduling.min_heap import MinHeap

from curator.form_curator import FormCurator

log = logging.getLogger(__name__)

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


curator = None  # global curator object


def initialize_worker(context: GearToolkitContext, curator_type: Type[C]):
    """Initialize worker context, this function is executed once in each worker
    process upon its creation.

    Args:
        context: GearToolkitContext
        curator_type: Type of FormCurator subclass to use for curation
    """
    # Create a curator object for each process with a new SDK client
    global curator
    sdk_client = context.get_client()
    curator = curator_type(sdk_client=sdk_client)


def curate_subject(heap: MinHeap[FileModel]) -> None:
    """Defines a task function for curating the files captured in the heap.

    Assumes the files are all under the same participant.

    Args:
      heap: the min heap of file model objects for the participant
      curator: a FormCurator subclass
    """

    global curator
    assert curator, 'curator object expected'

    while len(heap) > 0:
        file_info = heap.pop()
        if not file_info:
            continue

        curator.curate_container(file_info.file_id)


class ProjectFormCurator:
    """Defines a curator for applying a FormCurator to the files in a
    project."""

    def __init__(self, heap_map: Dict[str, MinHeap[FileModel]]) -> None:
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
            filter_str='acquisition.label=|[UDS]')
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

        log.info("Curating %s files in %s/%s", len(response_model.data),
                 project.group, project.label)

        subject_heap_map: Dict[str, MinHeap[FileModel]] = {}
        for file_info in response_model.data:
            heap = subject_heap_map.get(file_info.subject_id,
                                        MinHeap[FileModel]())
            heap.push(file_info)
            subject_heap_map[file_info.subject_id] = heap

        return ProjectFormCurator(heap_map=subject_heap_map)

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

    def apply(self, context: GearToolkitContext,
              curator_type: Type[C]) -> None:
        """Applies a FormCurator to the form files in this project.

        Args:
          curator: a FormCurator subclass
        """

        log.info("Start curator for %s subjects", len(self.__heap_map))
        process_count = max(4, self.__compute_cores())
        with multiprocessing.Pool(processes=process_count,
                                  initializer=initialize_worker,
                                  initargs=(
                                      context,
                                      curator_type,
                                  )) as pool:
            for subject_id, heap in self.__heap_map.items():
                log.info("Curating files for subject %s", subject_id)
                pool.apply_async(curate_subject, (heap, ))
            pool.close()
            pool.join()


class ProjectCurationError(Exception):
    """Exception for errors curating project files."""
