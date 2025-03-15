import json
import logging
from datetime import datetime
from string import Template
from typing import Any, Dict, List, Literal, Optional, TypedDict

import yaml
from flywheel.file_spec import FileSpec
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from flywheel_adaptor.hierarchy_creator import (
    HierarchyCreationClient,
    HierarchyCreationError,
)
from flywheel_adaptor.subject_adaptor import (
    ParticipantVisits,
    SubjectAdaptor,
    SubjectError,
)
from keys.keys import DefaultValues, FieldNames
from outputs.errors import (
    FileError,
    ListErrorWriter,
    system_error,
    update_error_log_and_qc_metadata,
)
from pydantic import BaseModel, Field
from utils.utils import handle_acquisition_upload, update_file_info_metadata

log = logging.getLogger(__name__)


class VisitMapping(TypedDict):
    subject: SubjectAdaptor
    visits: ParticipantVisits


class LabelTemplate(BaseModel):
    """Defines a string template object for generating labels using input data
    from file records."""
    template: str
    transform: Optional[Literal['upper', 'lower']] = Field(default=None)

    def instantiate(self,
                    record: Dict[str, Any],
                    *,
                    environment: Optional[Dict[str, Any]] = None) -> str:
        """Instantiates the template using the data from the record matching
        the variables in the template. Converts the generated label to upper or
        lower case if indicated for the template.

        Args:
          record: data record
          env: environment variable settings
        Returns:
          the result of substituting values from the record.
        Raises:
          ValueError if a variable in the template does not occur in the record
        """
        result = self.template
        try:
            result = Template(self.template).substitute(record)
        except KeyError as error:
            if not environment:
                raise ValueError(
                    f"Error creating label, missing column {error}") from error

        if environment:
            try:
                result = Template(result).substitute(environment)
            except KeyError as error:
                raise ValueError(
                    f"Error creating label, missing column {error}") from error

        if self.transform == 'lower':
            return result.lower()

        if self.transform == 'upper':
            return result.upper()

        return result


class UploadTemplateInfo(BaseModel):
    """Defines model for label template input."""
    session: LabelTemplate
    acquisition: LabelTemplate
    filename: LabelTemplate


class JSONUploader:
    """Generalizes upload of a record to an acquisition as JSON."""

    def __init__(self,
                 *,
                 proxy: FlywheelProxy,
                 project: ProjectAdaptor,
                 hierarchy_client: HierarchyCreationClient,
                 environment: Optional[Dict[str, Any]] = None,
                 template_map: UploadTemplateInfo) -> None:
        self.__proxy = proxy
        self.__project = project
        self.__hierarchy_client = hierarchy_client
        self.__session_template = template_map.session
        self.__acquisition_template = template_map.acquisition
        self.__filename_template = template_map.filename
        self.__environment = environment if environment else {}

    def upload(self, records: Dict[str, List[Dict[str, Any]]]) -> bool:
        """Uploads the records to acquisitions under the subject.

        Args:
          records: map from subject to list of records
        Returns:
          True if the file for each record is successfully saved
        """
        success = True
        for subject_label, record_list in records.items():

            for record in record_list:
                self.upload_record(subject_label=subject_label, record=record)

        return success

    def upload_record(self,
                      subject_label: str,
                      record: Dict[str, Any],
                      skip_duplicates: bool = True) -> None:
        """Uploads the serialized record to the subject with the session,
        acquisition, and file determined by the template of this object.

        Args:
          subject: the subject
          record: the record data
          skip_duplicates: Whether or not to skip duplicates
        Raises:
          UploaderError or ApiException if a failure occurs during the upload
        """
        session_label = self.__session_template.instantiate(record)
        acquisition_label = self.__acquisition_template.instantiate(record)
        try:
            file_ancestors = self.__hierarchy_client.create_hierarchy(
                project=self.__project,
                subject_label=subject_label,
                session_label=session_label,
                acquisition_label=acquisition_label)
        except HierarchyCreationError as error:
            raise UploaderError(
                'Failed to create hierarchy for '
                f'{subject_label}/{session_label}/{acquisition_label}: {error}'
            ) from error

        acquisition = self.__proxy.get_acquisition(
            file_ancestors.acquisition_id)  # type: ignore
        filename = self.__filename_template.instantiate(
            record, environment=self.__environment)

        handle_acquisition_upload(acquisition=acquisition,
                                  filename=filename,
                                  contents=json.dumps(record),
                                  content_type='application/json',
                                  subject_label=subject_label,
                                  session_label=session_label,
                                  acquisition_label=acquisition_label,
                                  skip_duplicates=skip_duplicates)


class FormJSONUploader:

    def __init__(self, project: ProjectAdaptor, module: str, gear_name: str,
                 error_writer: ListErrorWriter) -> None:
        self.__project = project
        self.__module = module
        self.__gear_name = gear_name
        self.__error_writer = error_writer
        self.__pending_visits: Dict[str, VisitMapping] = {}

    def __add_pending_visit(self, *, subject: SubjectAdaptor, filename: str,
                            file_id: str, input_record: Dict[str, Any]):
        """Add the visit to the list of visits pending for QC for the
        participant.

        Args:
            subject: Flywheel subject adaptor for the participant
            filename: Flywheel acquisition file name
            file_id: Flywheel acquisition file ID
            input_record: input visit data
        """
        visit_mapping: VisitMapping
        subject_lbl = input_record[FieldNames.NACCID]
        if subject_lbl in self.__pending_visits:
            visit_mapping = self.__pending_visits[subject_lbl]
            visit_mapping['visits'].add_visit(
                filename=filename,
                file_id=file_id,
                visitdate=input_record[FieldNames.DATE_COLUMN])
        else:
            participant_visits = ParticipantVisits.create_from_visit_data(
                filename=filename, file_id=file_id, input_record=input_record)
            visit_mapping = {'subject': subject, 'visits': participant_visits}
            self.__pending_visits[subject_lbl] = visit_mapping

    def __create_pending_visits_file(self) -> bool:
        """Create and upload a pending visits file for each participant module.
        These files will trigger the form-qc-coordinator gear for respective
        Flywheel subject.

        Returns:
            True if upload is successful, else False
        """

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        success = True
        for participant, visits_mapping in self.__pending_visits.items():
            subject = visits_mapping['subject']
            visits = visits_mapping['visits']
            yaml_content = yaml.safe_dump(
                data=visits.model_dump(serialize_as_any=True),
                allow_unicode=True,
                default_flow_style=False)
            filename = f'{participant}-{self.__module}-visits-pending-qc-{timestamp}.yaml'  # NOQA E501
            file_spec = FileSpec(name=filename,
                                 contents=yaml_content,
                                 content_type='application/yaml')
            try:
                subject.upload_file(file_spec)
                log.info('Uploaded file %s to subject %s', filename,
                         participant)
            except SubjectError as error:
                success = False
                log.error(error)

        return success

    def __update_visit_error_log(self,
                                 *,
                                 error_log_name: str,
                                 status: str,
                                 error_obj: Optional[FileError] = None):
        """Update error log file for the visit and store error metadata in
        file.info.qc.

        Args:
            error_log_name: error log file name
            status: visit file upload status [PASS|FAIL]
            error_obj (optional): error object, if there're any errors
        """

        if error_obj:
            self.__error_writer.write(error_obj)

        if not update_error_log_and_qc_metadata(
                error_log_name=error_log_name,
                destination_prj=self.__project,
                gear_name=self.__gear_name,
                state=status,
                errors=self.__error_writer.errors()):
            log.error('Failed to update visit error log file %s',
                      error_log_name)

    def upload(
            self,
            participant_records: Dict[str, Dict[str, Dict[str, Any]]]) -> bool:
        """Converts a transformed CSV record to a JSON file and uploads it to
        the respective acquisition in Flywheel.

        - If the record already exists in Flywheel (duplicate), it will not be uploaded.
        - If the record is new/modified, upload it to Flywheel and update file metadata.

        Args:
            participant_visits: set of visits to upload, by participant

        Returns:
            bool: True if uploads are successful
        """

        success = True
        for subject_lbl, visits_info in participant_records.items():
            subject = self.__project.find_subject(label=subject_lbl)
            if not subject:
                log.info('Adding new subject %s', subject_lbl)
                subject = self.__project.add_subject(subject_lbl)

            for log_file, record in visits_info.items():
                self.__error_writer.clear()
                session_label = DefaultValues.SESSION_LBL_PRFX + \
                    record[FieldNames.VISITNUM]

                acq_label = record[FieldNames.MODULE].upper()

                visit_file_name = subject.get_acquisition_file_name(
                    session=session_label, acquisition=acq_label)
                try:
                    new_file = subject.upload_acquisition_file(
                        session_label=session_label,
                        acquisition_label=acq_label,
                        filename=visit_file_name,
                        contents=json.dumps(record),
                        content_type='application/json')
                except (SubjectError, TypeError) as error:
                    log.error(error)
                    self.__update_visit_error_log(
                        error_log_name=log_file,
                        status='FAIL',
                        error_obj=system_error(message=str(error)))
                    success = False
                    continue

                # No error and no new file (i.e. duplicate file exists)
                # this cannot happen as duplicate visits detected earlier in the process
                if not new_file:
                    log.error('Existing duplicate visit file %s',
                              visit_file_name)
                    success = False
                    continue

                if not update_file_info_metadata(new_file, record):
                    self.__update_visit_error_log(
                        error_log_name=log_file,
                        status='FAIL',
                        error_obj=system_error(
                            message=
                            f'Error in setting file {visit_file_name} metadata'
                        ))
                    success = False
                    continue

                self.__update_visit_error_log(error_log_name=log_file,
                                              status='PASS')

                self.__add_pending_visit(subject=subject,
                                         filename=visit_file_name,
                                         file_id=new_file.id,
                                         input_record=record)

        success = success and self.__create_pending_visits_file()
        return success


class UploaderError(Exception):
    pass
