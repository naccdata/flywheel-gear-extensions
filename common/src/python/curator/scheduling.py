"""Scheduling for project curation."""

import logging
import multiprocessing
from multiprocessing.pool import Pool
import os
from typing import List

from curator.curator import Curator, ProjectCurationError
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel.models.subject import Subject
from fw_gear import GearContext
from nacc_attribute_deriver.symbol_table import SymbolTable
from pydantic import ValidationError
from scheduling.min_heap import MinHeap

from .scheduling_models import FileModel, ViewResponseModel

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


def build_file_heap(subject: Subject) -> MinHeap[FileModel]:
    """Build file heap for the given subject."""
    # create dataview for files in subject
    global curator
    assert curator, "curator object expected"

    with curator.read_dataview(subject.id) as response:
        response_data = response.read()
        try:
            response_model = ViewResponseModel.model_validate_json(response_data)
        except ValidationError as error:
            raise ProjectCurationError(
                f"Error curating subject {subject.label}: {error}"
            ) from error

    # associate UDS sessions; fail whole subject if a duplicate session is found
    heap = MinHeap[FileModel]()
    try:
        response_model.associate_uds_session()
    except ValueError as error:
        log.error(f"{subject.label} failed, clearing curation: {error}")
        # clear out curation tags on all files
        for file_model in response_model.data:
            curator.clear_curation_tag(file_model)

        # write error
        curator.handle_curation_failure(subject, str(error))
        return heap

    log.debug("Curating %s files in for %s", len(response_model.data), subject.label)
    for file_model in response_model.data:
        if not file_model.visit_pass:
            log.warning("ignoring unexpected file %s", file_model.filename)
            continue

        heap.push(file_model)

    return heap


def curate_subject(subject_id: str) -> None:
    """Defines a task function for curating the files captured in the heap.
    Assumes the files are all under the same participant.

    Args:
        subject_id: ID of subject this heap belongs to
    """
    global curator
    assert curator, "curator object expected"

    subject = curator.get_subject(subject_id)
    subject = subject.reload()
    subject_table = SymbolTable(subject.info)

    heap = build_file_heap(subject)
    if not heap:
        log.warning(f"No files to curate for subject {subject.label}")
        return

    log.debug(f"Curating {len(heap)} files for {subject.label}")

    curator.pre_curate(subject, subject_table)
    processed_files: List[FileModel] = []

    while len(heap) > 0:
        file_model = heap.pop()
        if not file_model:
            continue

        if curator.curate_file(subject, subject_table, file_model):
            processed_files.append(file_model)

    curator.post_curate(subject, subject_table, processed_files)


class ProjectCurationScheduler:
    """Defines a curator for applying a FormCurator to the files in a
    project."""

    def __init__(
        self,
        project: ProjectAdaptor,
        include_subjects: List[str],
        exclude_subjects: List[str],
    ) -> None:
        """Initializer.

        Args:
            project: The project to curate over
            filename_patterns: The filename patterns to curate over
        """
        self.__project = project
        self.__include_subjects = include_subjects
        self.__exclude_subjects = exclude_subjects

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

    def apply(
        self, curator: Curator, context: GearContext, max_num_workers: int = 4
    ) -> None:
        """Applies a Curator to the form files in this curator.

        Args:
          curator: an instantiated curator class
          context: context to set SDK client from
          include_subjects: Subjects to include in curation
          exclude_subjects: Subjects to exclude in
          max_num_workers: max number of workers to use
        """
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
            for subject in self.__project.project.subjects.iter():
                if (
                    self.__include_subjects
                    and subject.label not in self.__include_subjects
                ):
                    continue
                if self.__exclude_subjects and subject.label in self.__exclude_subjects:
                    continue

                log.debug("Curating subject %s", subject.id)
                results.append(
                    pool.apply_async(
                        curate_subject,
                        (subject.id,),
                    )
                )

            pool.close()
            for r in results:  # checks for exceptions
                r.get()

            pool.join()
