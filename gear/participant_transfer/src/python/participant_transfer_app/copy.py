"""Module for copying transferred participant data."""

import logging
from typing import Any, Dict, List

from centers.center_group import CenterGroup, CenterStudyMetadata
from flywheel import Project
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from gear_execution.gear_trigger import trigger_gear
from jobs.job_poll import JobPoll

log = logging.getLogger(__name__)


class CopyHelper:
    """This class soft links participant data from previous center to new
    center."""

    def __init__(
        self,
        *,
        subject_label: str,
        proxy: FlywheelProxy,
        new_center: CenterGroup,
        prev_center: CenterGroup,
        datatypes: List[str],
        warnings: List[str],
    ) -> None:
        self.__subject_label = subject_label
        self.__proxy = proxy
        self.__new_center = new_center
        self.__prev_center = prev_center
        self.__datatypes = datatypes
        self.__warnings = warnings
        self.__jobs_list: List[str] = []

    def __copy_project_data(
        self, source_project_id: str, target_project_id: str
    ) -> bool:
        """Copy participant data from a project in previous center to a project
        in new center.

        Args:
            source_project_id: Flywheel project id for previous center project
            target_project_id: Flywheel project id for new center project

        Returns:
            bool: True if soft-copy job successfully queued
        """
        source_project = self.__prev_center.get_project_by_id(source_project_id)
        if not source_project:
            log.error(f"Failed to find source project by ID {source_project_id}")
            return False

        # Skip if participant has no data in source project
        if not source_project.find_subject(label=self.__subject_label):
            message = (
                f"Participant {self.__subject_label} not found in "
                f"{self.__prev_center.label}/{source_project.label}"
            )
            log.warning(message)
            self.__warnings.append(message)
            return True

        target_project = self.__new_center.get_project_by_id(target_project_id)
        if not target_project:
            log.error(f"Failed to find destination project by ID {target_project_id}")
            return False

        gear_configs = {
            "debug": False,
            "duplicate-strategy": "replace",
            "include-filter": f"subject.label={self.__subject_label}",
            "target-project": f"{target_project_id}",
        }

        return self.__trigger_soft_copy_gear(
            gear_configs=gear_configs, destination=source_project.project
        )

    def __trigger_soft_copy_gear(
        self, gear_configs: Dict[str, Any], destination: Project
    ) -> bool:
        """Trigger the soft-copy gear.

        Args:
            gear_configs: gear configs dictionary
            destination: Flywheel project to run the gear

        Returns:
            bool: True if soft-copy job successfully queued
        """
        job_id = trigger_gear(
            proxy=self.__proxy,
            gear_name="soft-copy",
            config=gear_configs,
            destination=destination,
        )

        if not job_id:
            log.error(
                f"Failed to trigger soft-copy gear for subject {self.__subject_label} "
                f"in project {destination.group}/{destination.label}"
            )
            return False

        log.info(
            f"Queued soft-copy gear for subject {self.__subject_label} "
            f"in project {destination.group}/{destination.label}: Job ID {job_id}"
        )
        self.__jobs_list.append(job_id)

        return True

    def __copy_ingest_projects(
        self,
        prev_center_info: CenterStudyMetadata,
        new_center_info: CenterStudyMetadata,
    ) -> bool:
        """Copy participant data in ingest projects
        Args:
            prev_center_info: Study metadata for previous center
            new_center_info: Study metadata for new center

        Returns:
            bool: True if data copied successfully
        """
        ingest_projects = prev_center_info.ingest_projects
        if not ingest_projects:
            log.info(
                "No ingest projects metadata found for "
                f"center {self.__prev_center.label} study {prev_center_info.study_id}"
            )
            return True

        for source_project in ingest_projects.values():
            if (
                source_project.datatype in self.__datatypes
                and source_project.project_label.startswith(
                    "ingest-"
                )  # skip sandbox projects
            ):
                dest_project = new_center_info.get_ingest(source_project.project_label)
                if not dest_project:
                    message = (
                        f"Ingest project {source_project.project_label} "
                        f"not found in center {self.__new_center.label} metadata"
                    )
                    log.warning(message)
                    self.__warnings.append(message)
                    continue

                if not self.__copy_project_data(
                    source_project.project_id, dest_project.project_id
                ):
                    return False

        return True

    def __copy_distribution_projects(
        self,
        prev_center_info: CenterStudyMetadata,
        new_center_info: CenterStudyMetadata,
    ) -> bool:
        """Copy participant data in distribution projects
        Args:
            prev_center_info: StudyMetadata for previous center
            new_center_info: StudyMetadata for new center

        Returns:
            bool: True if data copied successfully
        """
        dist_projects = prev_center_info.distribution_projects
        if not dist_projects:
            log.info(
                "No distribution projects metadata found for "
                f"center {self.__prev_center.label} study {prev_center_info.study_id}"
            )
            return True

        for source_project in dist_projects.values():
            if source_project.datatype in self.__datatypes:
                dest_project = new_center_info.get_distribution(
                    source_project.project_label
                )
                if not dest_project:
                    message = (
                        f"Distribution project {source_project.project_label} "
                        f"not found in center {self.__new_center.label} metadata"
                    )
                    log.warning(message)
                    self.__warnings.append(message)
                    continue

                if not self.__copy_project_data(
                    source_project.project_id, dest_project.project_id
                ):
                    return False

        return True

    def copy_participant(self) -> bool:
        new_center_metadata = self.__new_center.get_project_info()
        prev_center_metadata = self.__prev_center.get_project_info()

        for study_id, study_info in prev_center_metadata.studies.items():
            new_center_info = new_center_metadata.get(study_id=study_id)
            if not new_center_info:
                message = (
                    f"Study {study_id} not found in center "
                    f"{self.__new_center.label} metadata"
                )
                log.warning(message)
                self.__warnings.append(message)
                continue

            if not self.__copy_ingest_projects(
                prev_center_info=study_info, new_center_info=new_center_info
            ):
                return False

            if not self.__copy_distribution_projects(
                prev_center_info=study_info, new_center_info=new_center_info
            ):
                return False

        return True

    def monitor_job_status(self) -> bool:
        """Monitor the status of queued soft-copy jobs.

        Returns:
            bool: True if all jobs completed, else False
        """
        log.info(f"Waiting for {len(self.__jobs_list)} soft-copy jobs to complete")
        failed_list = []
        for job_id in self.__jobs_list:
            if not JobPoll.is_job_complete(self.__proxy, job_id):
                failed_list.append(job_id)

        if failed_list:
            log.error(f"Failed Jobs: {failed_list}")
            return False

        return True
