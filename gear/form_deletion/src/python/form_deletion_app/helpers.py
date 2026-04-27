"""Helper classes for deleting a form visit."""

import logging
from typing import List, Optional

from configs.ingest_configs import FormProjectConfigs, ModuleConfigs, UploadTemplateInfo
from deletions.models import DeletedItems, DeleteRequest
from flywheel.models.file_entry import FileEntry
from flywheel.models.project import Project
from flywheel.models.session import Session
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, SubjectAdaptor
from nacc_common.field_names import FieldNames

log = logging.getLogger(__name__)


class AcquisitionRemover:
    """Class to delete acquisition files for a form delete request, including
    any dependent module acquisitions."""

    def __init__(
        self,
        *,
        proxy: FlywheelProxy,
        module: str,
        naccid: str,
        form_configs: FormProjectConfigs,
        module_configs: ModuleConfigs,
        delete_request: DeleteRequest,
        dependent_modules: Optional[List[str]] = None,
        deleted_items: DeletedItems,
    ):
        """
        Args:
            proxy: the Flywheel proxy
            module: the primary module name
            naccid: the NACC ID for the subject
            form_configs: form ingest configs
            module_configs: ingest configs for the primary module
            delete_request: the form delete request
            dependent_modules: associated modules for the current module, if present
            deleted_items: list of items deleted while processing this request
        """
        self.__proxy = proxy
        self.__module = module
        self.__naccid = naccid
        self.__form_configs = form_configs
        self.__module_configs = module_configs
        self.__delete_request = delete_request
        self.__dependent_modules = dependent_modules
        self.__deleted = deleted_items

    def __compare_visit_details(self, *, acq_file: FileEntry, date_field: str) -> bool:
        """Compares the file's info.forms.json fields with the delete request.

        Args:
            acq_file: the acquisition file entry
            date_field: date field name for the module

        Returns:
            True if the file's forms.json fields match the delete request,
            False otherwise
        """

        acq_file = acq_file.reload()
        if not acq_file.info:
            return True

        forms_json = acq_file.info.get("forms", {}).get("json", {})
        if not forms_json:
            return True

        ptid = forms_json.get(FieldNames.PTID)
        if ptid and ptid != self.__delete_request.ptid:
            log.error(
                f"PTID mismatch, value in acquisition file {ptid}, "
                f"value in delete request {self.__delete_request.ptid}"
            )
            return False

        date = forms_json.get(date_field)
        if date and date != self.__delete_request.visitdate:
            log.error(
                f"visitdate mismatch, value in acquisition file {date}, "
                f"value in delete request {self.__delete_request.visitdate}"
            )
            return False

        visitnum = forms_json.get(FieldNames.VISITNUM)
        if visitnum and visitnum != self.__delete_request.visitnum:
            log.error(
                f"visitnum mismatch, value in acquisition file {visitnum}, "
                f"value in delete request {self.__delete_request.visitnum}"
            )
            return False

        return True

    def __build_hierarchy_labels(
        self,
        *,
        module: str,
        date_field: str,
        hierarchy_labels: UploadTemplateInfo,
        subject_label: str,
    ) -> Optional[tuple[str, str, str]]:
        """Derives Flywheel container labels from templates and the delete
        request.

        Returns:
            Tuple of (session_label, acquisition_label, filename),
            or None if derivation fails.
        """

        record = {
            "module": module,
            date_field: self.__delete_request.visitdate,
            "visitnum": self.__delete_request.visitnum,
        }
        try:
            session_label = hierarchy_labels.session.instantiate(record=record)
            acquisition_label = hierarchy_labels.acquisition.instantiate(record=record)
            filename = hierarchy_labels.filename.instantiate(
                record=record,
                environment={
                    "subject": subject_label,
                    "session": session_label,
                    "acquisition": acquisition_label,
                },
            )
        except ValueError as error:
            log.error(
                f"Failed to derive Flywheel container labels for "
                f"{subject_label}/{module} from this delete request: {error}"
            )
            return None
        return session_label, acquisition_label, filename

    def __delete_module_acquisition(
        self,
        *,
        subject: SubjectAdaptor,
        project: Project,
        module: str,
        date_field: str,
        hierarchy_labels: UploadTemplateInfo,
        remove_empty_session: bool = False,
    ) -> bool:
        """Deletes the acquisition for a given module.

        Args:
            subject: Flywheel SubjectAdaptor
            project: Flywheel project to remove the acquisitions from
            module: the module name
            date_field: date field name for the module
            hierarchy_labels: session/acquisition/filename label templates
            remove_empty_session: whether to remove the session if empty

        Returns:
            True if the acquisition was successfully deleted, False otherwise
        """
        labels = self.__build_hierarchy_labels(
            module=module,
            date_field=date_field,
            hierarchy_labels=hierarchy_labels,
            subject_label=subject.label,
        )
        if not labels:
            return False

        session_label, acquisition_label, filename = labels

        session = subject.sessions.find_first(f"label={session_label}")
        if not session:
            log.info(
                f"Session {session_label} not found in "
                f"{project.group}/{project.label}/{subject.label}"
            )
            return True

        acquisition = session.acquisitions.find_first(f"label={acquisition_label}")
        if not acquisition:
            log.info(
                f"Acquisition {acquisition_label} not found in "
                f"{project.group}/{project.label}/{subject.label}/{session_label}"
            )
            return True

        acq_file = acquisition.get_file(filename)
        if not acq_file:
            log.warning(
                f"Acquisition file {filename} not found in "
                f"{project.group}/{project.label}/{subject.label}/{session_label}"
            )
            return True

        if not self.__compare_visit_details(acq_file=acq_file, date_field=date_field):
            log.warning(
                f"File metadata in {filename} does not match the delete request"
            )
            return False

        if not self.__proxy.delete_acquisition(acquisition.id):
            log.error(
                f"Failed to delete acquisition {filename} from"
                f"{project.group}/{project.label}/{subject.label}/{session_label}"
            )
            return False

        lfv_info = subject.get_last_failed_visit(module=module)
        if lfv_info and lfv_info.filename == filename:
            log.info(
                f"Resetting last failed visit {filename} "
                f"in {project.group}/{project.label}"
            )
            subject.reset_last_failed_visit(module=module)

        self.__deleted.acquisitions.append(
            f"{project.group}/{project.label}/{filename}"
        )

        if remove_empty_session:
            return self.__delete_empty_session(
                session=session,
                project=project,
                subject_label=subject.label,
                session_label=session_label,
            )

        return True

    def __delete_empty_session(
        self,
        *,
        session: Session,
        project: Project,
        subject_label: str,
        session_label: str,
    ) -> bool:
        """Deletes the session if it has no remaining acquisitions.

        Returns:
            True if the session was deleted or still has acquisitions,
            False if deletion failed.
        """
        session = session.reload()
        if len(session.acquisitions()) == 0:  # type: ignore
            if not self.__proxy.delete_session(session.id):
                log.error(
                    f"Failed to delete session "
                    f"{project.group}/{project.label}/{subject_label}/{session_label}"
                )
                return False

            self.__deleted.sessions.append(
                f"{project.group}/{project.label}/{subject_label}/{session_label}"
            )

        return True

    def __delete_acquisition_files(
        self, subject: SubjectAdaptor, project: Project
    ) -> bool:
        """Deletes acquisition files for the primary module and any dependent
        modules for the specified project/subject.

        Args:
            subject: Flywheel SubjectAdaptor
            project: Flywheel project to remove the acquisitions from

        Returns:
            True if all deletions succeeded, False if any failed
        """

        success = True
        if self.__dependent_modules:
            # delete any associated module files first (if present)
            for dep_module in self.__dependent_modules:
                dep_configs = self.__form_configs.module_configs.get(dep_module)
                if not dep_configs:
                    log.error(
                        f"No module configs found for dependent module {dep_module}"
                    )
                    success = False
                    continue

                if not self.__delete_module_acquisition(
                    subject=subject,
                    project=project,
                    module=dep_module,
                    date_field=dep_configs.date_field,
                    hierarchy_labels=dep_configs.hierarchy_labels,
                ):
                    success = False

        return (
            self.__delete_module_acquisition(
                subject=subject,
                project=project,
                module=self.__module,
                date_field=self.__module_configs.date_field,
                hierarchy_labels=self.__module_configs.hierarchy_labels,
                remove_empty_session=True,
            )
            and success
        )

    def cleanup_acquisitions(self) -> bool:
        """Deletes the respective acquisitions form the form ingest project and
        the accepted project for the center.

        Returns:
            True if all deletions succeeded, False if any failed
        """
        log.info(
            f"Removing acquisitions for "
            f"PTID {self.__delete_request.ptid} ({self.__naccid}), "
            f"visitdate {self.__delete_request.visitdate}"
        )

        success = True
        subjects = self.__proxy.get_subject_by_label(label=self.__naccid)
        if not subjects:
            # This is possible if a NACCID generated but no sessions created yet
            log.warning(f"Cannot find any subjects with NACCID {self.__naccid}")
            return True

        if (
            self.__module_configs.hierarchy_labels.session.template.find("visitnum")
            != -1
            and not self.__delete_request.visitnum
        ):
            log.error(
                "Require visitnum to derive the session label for "
                f"{self.__naccid}/{self.__module}/{self.__delete_request.visitdate}"
            )
            return False

        # List of form projects to check for matching acquisitions
        # Do not include retrospective-form here, not removing legacy data
        prefixes = ("ingest-form", "sandbox-form", "accepted")

        for subject in subjects:
            project: Optional[Project] = self.__proxy.get_project_by_id(
                subject.parents.project
            )
            if not project:
                log.warning(
                    "Failed to find parent project with ID "
                    f"{subject.parents.project} for {self.__naccid}"
                )
                continue

            log.info(
                f"{self.__naccid} found in project {project.group}/{project.label}"
            )

            if not project.label.startswith(prefixes):
                # skip other projects
                continue

            success = (
                self.__delete_acquisition_files(
                    subject=SubjectAdaptor(subject), project=project
                )
                and success
            )

            subject = subject.reload()
            # If there are no more sessions, delete the subject
            if len(subject.sessions()) == 0:  # type: ignore
                if not self.__proxy.delete_subject(subject_id=subject.id):
                    log.error(
                        f"Failed to delete subject {subject.label} "
                        f"from {project.group}/{project.label}"
                    )
                    success = False
                    continue

                self.__deleted.subjects.append(
                    f"{project.group}/{project.label}/{subject.label}"
                )

        return success
