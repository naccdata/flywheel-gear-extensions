"""Scheduling for project curation."""
import logging
from datetime import date, datetime
import multiprocessing
from multiprocessing.pool import Pool
import os
import re
from typing import Any, Dict, List, Literal, Optional

from curator.curator import Curator
from dataview.dataview import ColumnModel, make_builder
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_gear_toolkit import GearToolkitContext
from pydantic import BaseModel, ValidationError, field_validator
from scheduling.min_heap import MinHeap

log = logging.getLogger(__name__)


class FileModel(BaseModel):
    """Defines data model for columns returned from the project form curator
    data model.

    Objects are ordered by order date.
    """
    filename: str
    file_id: str
    acquisition_id: str
    subject_id: str
    modified_date: date
    visit_date: Optional[date]
    study_date: Optional[date]
    scan_date: Optional[date]
    scandate: Optional[date]
    scandt: Optional[date]

    @property
    def visit_pass(self) -> Optional[Literal['pass0', 'pass1', 'pass2']]:
        """Returns the "pass" for the file; determining when the relative order
        of when the file should be visited.

        Passes are based on the dependency of attributes over the files.
        The pass is determined by matching the file with a regular expression.

        Order of curation is indicated by inverse lexicographical ordering on
        the pass name.
        This is done to avoid having to maintain the total ordering without
        having to rename the pass if more constraints are added.

        As it is, UDS must be curated last; after every other file.
        Historical APOE must be curated before the NCRAD APOE.
        As such, there are currently 3 pass categories.
        """
        # need to handle historic apoe separately as it does not work well with regex
        if 'historic_apoe_genotype' in self.filename:
            return 'pass2'

        pattern = (
            r"^"
            r"(?P<pass1>.+("
            r"_NP|_MDS|_MLST|"
            r"apoe_genotype|NCRAD-SAMPLES.+|niagads_availability|"
            r"SCAN-MR-QC.+|SCAN-MR-SBM.+|"
            r"SCAN-PET-QC.+|SCAN-AMYLOID-PET-GAAIN.+|SCAN-AMYLOID-PET-NPDKA.+|"
            r"SCAN-FDG-PET-NPDKA.+|SCAN-TAU-PET-NPDKA.+"
            r")\.json)|"
            r"(?P<pass0>.+(_UDS|_MEDS)\.json)"
            r"$")
        match = re.match(pattern, self.filename)
        if not match:
            return None

        groups = match.groupdict()
        names = {key for key in groups if groups.get(key) is not None}
        if len(names) != 1:
            raise ValueError(f"error matching file name {self.filename}")

        return names.pop()  # type: ignore

    @property
    def order_date(self) -> date:
        """Returns the date to be used for ordering this file.

        Checks for form visit date, then scan date, and then file modification date.

        Returns:
          the date to be used to compare this file for ordering
        """
        if self.visit_date:
            return self.visit_date
        if self.study_date:
            return self.study_date
        if self.scan_date:
            return self.scan_date
        if self.scandate:
            return self.scandate
        if self.scandt:
            return self.scandt
        if self.modified_date:
            return self.modified_date

        raise ValueError(
            f"file {self.filename} {self.file_id} has no associated date")

    def __eq__(self, other) -> bool:
        if not isinstance(other, FileModel):
            return False

        return self.file_id == other.file_id

    def __lt__(self, other) -> bool:
        """Order the objects by order class and date.

        First, use inverse order on order-class: if the class is greater
        than, the object is less than. Second, order by date.
        """
        if not isinstance(other, FileModel):
            return False
        if not self.visit_pass or not other.visit_pass:
            raise ValueError(
                f"Cannot compare values {self.visit_pass} with {other.visit_pass}"
            )

        # Note: this inverts the order on the order_class
        if self.visit_pass > other.visit_pass:
            return True
        if self.visit_pass < other.visit_pass:
            return False

        return self.order_date < other.order_date

    @field_validator("modified_date",
                     "visit_date",
                     "study_date",
                     "scan_date",
                     "scandate",
                     "scandt",
                     mode='before')
    def datetime_to_date(cls,
                         value: Optional[date | str]) -> Optional[date | str]:
        if not value:
            return None

        if isinstance(value, date):
            return value

        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            pass

        return value


class ViewResponseModel(BaseModel):
    """Defines the data model for a dataview response."""
    data: List[FileModel]

    @field_validator("data", mode='before')
    def trim_data(cls, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove any rows that are completely empty, which can happen if the
        filename pattern does not match.

        Args:
            data: List of retrieved rows from the builder
        Returns:
            Trimmed data
        """
        return [
            row for row in data if any(x is not None for x in row.values())
        ]


curator = None  # global curator object


def initialize_worker(in_curator: Curator, context: GearToolkitContext):
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
    assert curator, 'curator object expected'
    subject = curator.get_subject(subject_id)

    curator.pre_process(subject)
    processed_files: List[str] = []

    while len(heap) > 0:
        file_info = heap.pop()
        if not file_info:
            continue

        curator.curate_file(subject, file_info.file_id)
        processed_files.append(file_info.file_id)

    curator.post_process(subject, processed_files)


class ProjectCurationScheduler:
    """Defines a curator for applying a FormCurator to the files in a
    project."""

    def __init__(self, heap_map: Dict[str, MinHeap[FileModel]]) -> None:
        self.__heap_map = heap_map

    @classmethod
    def create(
            cls,
            project: ProjectAdaptor,
            filename_pattern: str,
            blacklist: Optional[List[str]] = None
    ) -> 'ProjectCurationScheduler':
        """Creates a ProjectCurationScheduler for the projects.

        Pulls information for all of the files in the project.

        Note:Columns must correspond to fields of FileModel.

        Args:
          project: the project
          filename_pattern: Filename pattern to match on
          blacklist: List of subjects to ignore
        Returns:
          the ProjectCurationScheduler for the form files in the project
        """
        log.info("Creating project dataview")

        builder = make_builder(
            label='attribute-curation-scheduling',
            description='Lists files for curation',
            columns=[
                ColumnModel(data_key="file.name", label="filename"),
                ColumnModel(data_key="file.file_id", label="file_id"),
                ColumnModel(data_key="file.parents.acquisition",
                            label="acquisition_id"),
                ColumnModel(data_key="file.parents.subject",
                            label="subject_id"),
                ColumnModel(data_key='file.info.forms.json.visitdate',
                            label="visit_date"),
                ColumnModel(data_key="file.modified", label="modified_date"),
                ColumnModel(data_key="file.info.raw.study_date",
                            label="study_date"),
                ColumnModel(data_key="file.info.raw.scan_date",
                            label="scan_date"),
                ColumnModel(data_key="file.info.raw.scandate",
                            label="scandate"),
                ColumnModel(data_key="file.info.raw.scandt", label="scandt")
            ],
            container='acquisition',
            filename=filename_pattern,
            missing_data_strategy='none')
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
            if not file_info.visit_pass:
                log.warning("ignoring unexpected file %s", file_info.filename)
                continue

            subject_id = file_info.subject_id
            if blacklist and subject_id in blacklist:
                log.info(f"{subject_id} blacklisted, skipping")
                continue

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

    def apply(self, curator: Curator, context: GearToolkitContext) -> None:
        """Applies a Curator to the form files in this curator.

        Args:
          curator: an instantiated curator class
          context: context to set SDK client from
        """
        log.info("Start curator for %s subjects", len(self.__heap_map))

        process_count = max(4, self.__compute_cores())
        results = []

        with Pool(processes=process_count,
                  initializer=initialize_worker,
                  initargs=(
                      curator,
                      context,
                  )) as pool:
            for subject_id, heap in self.__heap_map.items():
                log.info("Curating subject %s", subject_id)
                results.append(
                    pool.apply_async(curate_subject, (
                        subject_id,
                        heap,
                    )))

            pool.close()
            for r in results:  # checks for exceptions
                r.get()

            pool.join()


class ProjectCurationError(Exception):
    """Exception for errors curating project files."""
