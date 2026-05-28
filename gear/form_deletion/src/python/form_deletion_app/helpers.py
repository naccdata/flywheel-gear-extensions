"""Helper classes for deleting a form visit."""

import logging
from typing import List, Optional

from configs.ingest_configs import FormProjectConfigs, ModuleConfigs, UploadTemplateInfo
from deletions.models import DeletedItems, DeleteRequest
from flywheel.models.file_entry import FileEntry
from flywheel.models.project import Project
from flywheel.models.session import Session
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from flywheel_adaptor.subject_adaptor import SubjectAdaptor, SubjectError
from keys.keys import MetadataKeys
from nacc_common.data_identification import DataIdentification
from nacc_common.field_names import FieldNames

log = logging.getLogger(__name__)


class AcquisitionRemover:
    """Class to delete acquisition files for a form delete request, including
    any dependent module acquisitions."""

    def __init__(
        self,
        *,
        proxy: FlywheelProxy,
        primary_project_id: str,
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
            primary_project_id: ID of the form ingest project
            module: the primary module name
            naccid: the NACC ID for the subject
            form_configs: form ingest configs
            module_configs: ingest configs for the primary module
            delete_request: the form delete request
            dependent_modules: associated modules for the current module, if present
            deleted_items: list of items deleted while processing this request
        """
        self.__proxy = proxy
        self.__primary_project = primary_project_id
        self.__module = module
        self.__naccid = naccid
        self.__form_configs = form_configs
        self.__module_configs = module_configs
        self.__delete_request = delete_request
        self.__dependent_modules = dependent_modules
        self.__deleted = deleted_items
        self.__orphaned: List[DataIdentification] = []

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

        try:
            lfv_info = subject.get_last_failed_visit(module=module)
            if lfv_info and lfv_info.filename == filename:
                log.info(
                    f"Resetting last failed visit {filename} "
                    f"in {project.group}/{project.label}"
                )
                subject.reset_last_failed_visit(module=module)
        except SubjectError as error:
            log.warning(error)

        self.__deleted.acquisitions.append(
            f"{project.group}/{project.label}/{filename}"
        )

        if remove_empty_session:
            return self.__delete_empty_session(
                session=session,
                subject=subject,
                project=project,
            )

        return True

    def __delete_empty_session(
        self,
        *,
        session: Session,
        subject: SubjectAdaptor,
        project: Project,
    ) -> bool:
        """Deletes the session if it has no remaining acquisitions.

        Args:
            session: Flywheel session container
            subject: Flywheel subject adaptor
            project: Flywheel project container

        Returns:
            True if the session was deleted or still has acquisitions,
            False if deletion failed.
        """
        session = session.reload()
        if len(session.acquisitions()) == 0:  # type: ignore
            if not self.__proxy.delete_session(session.id):
                log.error(
                    f"Failed to delete session "
                    f"{project.group}/{project.label}/{subject.label}/{session.label}"
                )
                return False

            self.__deleted.sessions.append(
                f"{project.group}/{project.label}/{subject.label}/{session.label}"
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

    def __delete_orphaned_module_acquisitions(  # noqa: C901
        self,
        *,
        subject: SubjectAdaptor,
        project: Project,
        module: str,
        module_configs: ModuleConfigs,
    ) -> bool:
        """Deletes all acquisitions labelled with the given module for the
        subject/project pair. Also, deletes the respective session if there are
        no more acquisitions.

        Args:
            subject: Flywheel subject adaptor
            project: Flywheel project container
            module: Label of the orphaned module
            module_configs: Ingest configs for the orphaned module

        Returns:
            True if all deletions succeeded, False if any failed
        """

        ptid_key = f"{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.PTID}"
        date_col_key = f"{MetadataKeys.FORM_METADATA_PATH}.{module_configs.date_field}"
        visitnum_key = f"{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.VISITNUM}"
        columns = [
            "file.name",
            "file.file_id",
            "file.parents.acquisition",
            "file.parents.session",
            date_col_key,
            ptid_key,
        ]

        if FieldNames.VISITNUM in module_configs.required_fields:
            columns.append(visitnum_key)

        results = self.__proxy.get_matching_acquisition_files_info(
            container_id=subject.id,
            dv_title=f"Orphaned {module} visits for {self.__naccid}",
            columns=columns,
            filters=f"acquisition.label={module}",
        )
        if not results:
            return True

        success = True
        deleted_acq_ids: set = set()
        session_ids: set = set()
        for result in results:
            filename = result["file.name"]

            if self.__delete_request.ptid != result[ptid_key]:
                log.error(
                    f"Orphaned visit {filename} PTID {result[ptid_key]} does not "
                    f"match with the delete request PTID {self.__delete_request.ptid}"
                )
                success = False
                continue

            acq_id = result.get("file.parents.acquisition")
            if not acq_id:
                continue

            # This is not normal, usually there is only one file in a form acquisition
            if acq_id in deleted_acq_ids:
                self.__deleted.acquisitions.append(
                    f"{project.group}/{project.label}/{filename}"
                )
                continue

            if not self.__proxy.delete_acquisition(acq_id):
                log.error(
                    f"Failed to delete orphaned {self.__naccid}/{module} "
                    f"acquisition file {filename}"
                )
                success = False
                continue

            deleted_acq_ids.add(acq_id)
            session_ids.add(result.get("file.parents.session"))
            self.__deleted.acquisitions.append(
                f"{project.group}/{project.label}/{filename}"
            )

            # Collect the orphaned visit details for the primary ingest project
            if self.__primary_project == project.id:
                self.__orphaned.append(
                    DataIdentification.from_visit_metadata(
                        ptid=result.get(ptid_key),
                        date=result.get(date_col_key),
                        visitnum=result.get(visitnum_key),
                        module=module,
                    )
                )

        session_ids.discard(None)
        for session_id in session_ids:
            session = self.__proxy.get_container_by_id(session_id)
            if session and not self.__delete_empty_session(
                session=session,  # type: ignore
                subject=subject,
                project=project,
            ):
                success = False

        return success

    def __cleanup_orphaned_modules_for_subject(
        self,
        *,
        subject: SubjectAdaptor,
        project: Project,
        orphan_modules: List[str],
    ) -> bool:
        """Removes orphaned acquisitions and cleans up empty containers for one
        subject/project pair.

        Args:
            subject: Flywheel subject adaptor
            project: Flywheel project container
            orphan_modules: List of orphaned module labels

        Returns:
            True if all operations succeeded, False if any failed
        """
        success = True
        for module in orphan_modules:
            # Delete the orphaned acquisitions if there are any
            # Delete empty sessions after removing all orphaned acquisitions
            module_configs = self.__form_configs.module_configs.get(module)
            if not module_configs:
                continue

            if not self.__delete_orphaned_module_acquisitions(
                subject=subject,
                project=project,
                module=module,
                module_configs=module_configs,
            ):
                success = False
                continue

            # Resets the last-failed-visit for the module in the subject metadata.
            try:
                subject.reset_last_failed_visit(module=module)
            except SubjectError as error:
                log.warning(error)

        return success

    def get_orphaned_visit_details(self) -> List[DataIdentification]:
        """Returns the list of orphaned visits that were deleted."""
        return self.__orphaned

    def cleanup_orphaned_acquisitions(self, orphan_modules: List[str]) -> bool:
        """Deletes all acquisitions for the given modules from ingest, sandbox,
        and accepted projects. Used when no clinical forms remain for a subject
        after a clinical form deletion.

        Does NOT touch retrospective-form — only ingest-form, sandbox-form,
        and accepted projects are modified.

        Args:
            orphan_modules: module labels whose acquisitions should all be
                            removed (e.g. ["NP", "MLST"])

        Returns:
            True if all deletions succeeded, False if any failed
        """
        log.info(f"Removing orphaned {orphan_modules} acquisitions for {self.__naccid}")

        subjects = self.__proxy.get_subject_by_label(label=self.__naccid)
        if not subjects:
            log.warning(f"Cannot find any subjects with NACCID {self.__naccid}")
            return True

        prefixes = ("ingest-form", "sandbox-form", "accepted")
        success = True
        for subject in subjects:
            project: Optional[Project] = self.__proxy.get_project_by_id(
                subject.parents.project
            )
            if not project:
                log.warning(
                    f"Failed to find parent project {subject.parents.project} "
                    f"for {self.__naccid}"
                )
                continue

            if not project.label.startswith(prefixes):
                continue

            log.info(
                f"{self.__naccid} found in project {project.group}/{project.label}"
            )

            if not self.__cleanup_orphaned_modules_for_subject(
                subject=SubjectAdaptor(subject),
                project=project,
                orphan_modules=orphan_modules,
            ):
                success = False
                continue

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

            if not self.__delete_acquisition_files(
                subject=SubjectAdaptor(subject), project=project
            ):
                success = False
                continue

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
