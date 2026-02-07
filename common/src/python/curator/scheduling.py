"""Scheduling for project curation."""

import logging
import multiprocessing
from multiprocessing.pool import Pool
import os
from typing import Dict, List

from curator.curator import Curator, ProjectCurationError
from data.dataview import ColumnModel, make_builder
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from fw_gear import GearContext
from nacc_attribute_deriver.symbol_table import SymbolTable
from pydantic import ValidationError
from scheduling.min_heap import MinHeap

from .scheduling_models import FileModel, ProcessedFile, ViewResponseModel

log = logging.getLogger(__name__)

curator = None  # global curator object


def initialize_worker(in_curator: Curator, context: GearContext):
    """Initialize worker context, this function is executed once in each worker
    process upon its creation.

    Args:
        in_curator: Curator to use for curation
        context: context to set SDK client from
    """
    # Make the curator global for spawned process
    global curator
    curator = in_curator
    curator.set_client(context)


def curate_subject(subject_id: str, heap: MinHeap[FileModel]) -> None:
    """Defines a task function for curating the files captured in the heap.
    Assumes the files are all under the same participant.

    Args:
        subject_id: ID of subject this heap belongs to
        heap: the min heap of file model objects for the participant
    """

    global curator
    assert curator, "curator object expected"
    subject = curator.get_subject(subject_id)
    subject = subject.reload()
    subject_table = SymbolTable(subject.info)

    curator.pre_curate(subject, subject_table)
    processed_files: List[ProcessedFile] = []

    while len(heap) > 0:
        file_model = heap.pop()
        if not file_model:
            continue

        processed_file = curator.curate_file(subject, subject_table, file_model.file_id)
        if processed_file.file_info:
            processed_files.append(processed_file)

    curator.post_curate(subject, subject_table, processed_files)


class ProjectCurationScheduler:
    """Defines a curator for applying a FormCurator to the files in a
    project."""

    def __init__(self, heap_map: Dict[str, MinHeap[FileModel]]) -> None:
        self.__heap_map = heap_map

    @classmethod
    def create(
        cls,
        project: ProjectAdaptor,
        filename_patterns: List[str],
    ) -> "ProjectCurationScheduler":
        """Creates a ProjectCurationScheduler for the projects.

        Pulls information for all of the files in the project.

        Note:Columns must correspond to fields of FileModel.

        Args:
          project: the project
          filename_pattern: List of filename patterns to match on
        Returns:
          the ProjectCurationScheduler for the form files in the project
        """
        log.info("Creating project dataview")

        builder = make_builder(
            label="attribute-curation-scheduling",
            description="Lists files for curation",
            columns=[
                ColumnModel(data_key="file.name", label="filename"),
                ColumnModel(data_key="file.file_id", label="file_id"),
                ColumnModel(
                    data_key="file.parents.acquisition", label="acquisition_id"
                ),
                ColumnModel(data_key="file.parents.subject", label="subject_id"),
                ColumnModel(
                    data_key="file.info.forms.json.visitdate", label="visit_date"
                ),
                ColumnModel(data_key="file.modified", label="modified_date"),
                ColumnModel(data_key="file.info.raw.study_date", label="study_date"),
                ColumnModel(data_key="file.info.raw.scan_date", label="scan_date"),
                ColumnModel(data_key="file.info.raw.scandate", label="scandate"),
                ColumnModel(data_key="file.info.raw.scandt", label="scandt"),
                ColumnModel(
                    data_key="file.info.header.dicom.StudyDate", label="img_study_date"
                ),
            ],
            container="acquisition",
            missing_data_strategy="none",
        )
        if filename_patterns:
            builder.file_filter(value="|".join(filename_patterns), regex=True)
            builder.file_container("acquisition")

        view = builder.build()

        with project.read_dataview(view) as response:
            response_data = response.read()
            try:
                response_model = ViewResponseModel.model_validate_json(response_data)
            except ValidationError as error:
                raise ProjectCurationError(
                    f"Error curating project {project.label}: {error}"
                ) from error

        log.info(
            "Curating %s files in %s/%s",
            len(response_model.data),
            project.group,
            project.label,
        )

        subject_heap_map: Dict[str, MinHeap[FileModel]] = {}
        for file_info in response_model.data:
            if not file_info.visit_pass:
                log.warning("ignoring unexpected file %s", file_info.filename)
                continue

            subject_id = file_info.subject_id
            heap = subject_heap_map.get(subject_id, MinHeap[FileModel]())
            heap.push(file_info)
            subject_heap_map[subject_id] = heap

        return ProjectCurationScheduler(heap_map=subject_heap_map)

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

    def get_subject_ids(self) -> List[str]:
        """Return list of all subject IDs (FW IDs) to curate."""
        return list(self.__heap_map.keys())

    def apply(
        self, curator: Curator, context: GearContext, max_num_workers: int = 4
    ) -> None:
        """Applies a Curator to the form files in this curator.

        Args:
          curator: an instantiated curator class
          context: context to set SDK client from
          max_num_workers: max number of workers to use
        """
        log.info("Start curator for %s subjects", len(self.__heap_map))

        process_count = max(max_num_workers, self.__compute_cores())
        results = []

        with Pool(
            processes=process_count,
            initializer=initialize_worker,
            initargs=(
                curator,
                context,
            ),
        ) as pool:
            for subject_id, heap in self.__heap_map.items():
                log.debug("Curating subject %s", subject_id)
                results.append(
                    pool.apply_async(
                        curate_subject,
                        (
                            subject_id,
                            heap,
                        ),
                    )
                )

            pool.close()
            for r in results:  # checks for exceptions
                r.get()

            pool.join()
