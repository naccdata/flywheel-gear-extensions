from abc import ABC, abstractmethod
import json
import logging
from datetime import datetime
from string import Template
from typing import Any, Dict, List, Literal, Optional, TypedDict

import yaml
from flywheel.file_spec import FileSpec
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_adaptor.subject_adaptor import (
    ParticipantVisits,
    SubjectAdaptor,
    SubjectError,
)
from keys.keys import DefaultValues, FieldNames
from pydantic import BaseModel, Field, RootModel
from utils.utils import update_file_info_metadata

log = logging.getLogger(__name__)


class VisitMapping(TypedDict):
    subject: SubjectAdaptor
    visits: ParticipantVisits


class UploadTemplateInfo(BaseModel):
    """Defines model for label template input."""
    type: Literal['session', 'acquisition', 'filename']
    template: str
    transform: Optional[Literal['upper', 'lower']] = Field(default=None)


class UploadTemplateList(RootModel):
    """Root model for serializing the upload template information."""
    root: List[UploadTemplateInfo]

    def __bool__(self) -> bool:
        return bool(self.root)

    def __iter__(self):
        return iter(self.root)

    def __getitem__(self, item) -> UploadTemplateInfo:
        return self.root[item]

    def __len__(self):
        return len(self.root)

    def append(self, template: UploadTemplateInfo) -> None:
        """Appends the template info to the list."""
        self.root.append(template)


class LabelTemplate:
    """Defines a string template object for generating labels using input data
    from file records."""

    def __init__(self, template_info: UploadTemplateInfo) -> None:
        self.__type = template_info.type
        self.__template = Template(template_info.template)
        self.__transform = template_info.transform

    def instantiate(self, record: Dict[str, Any]) -> str:
        """Instantiates the template using the data from the record matching
        the variables in the template. Converts the generated label to upper or
        lower case if indicated for the template.

        Args:
          record: data record
        Returns:
          the result of substituting values from the record.
        Raises:
          ValueError if a variable in the template does not occur in the record
        """
        try:
            result = self.__template.substitute(record)
        except KeyError as error:
            raise ValueError(
                f"Error creating {self.__type} label, missing column {error}"
            ) from error

        if self.__transform == 'lower':
            return result.lower()

        if self.__transform == 'upper':
            return result.upper()

        return result

class RecordUploader(ABC):
    
    @abstractmethod
    def upload(self, records: Dict[str, List[Dict[str, Any]]]) -> bool:
        """Uploads the records to acquisitions under the subject.
        
        Args:
          records: map from subject to list of records
        Returns:
          True if the file for each record is saved. False, otherwise.
        """

class JSONUploader(RecordUploader):
    """Generalizes upload of a record to an acquisition as JSON."""

    def __init__(self, project: ProjectAdaptor,
                 template_map: Dict[str, LabelTemplate]) -> None:
        self.__project = project
        self.__session_template = template_map['session']
        self.__acquisition_template = template_map['acquisition']
        self.__filename_template = template_map['filename']

    def upload(self, records: Dict[str, List[Dict[str, Any]]]) -> bool:
        """Uploads the records to acquisitions under the subject.

        Args:
          records: map from subject to list of records
        Returns:
          True if the file for each record is successfully saved
        """
        success = True
        for subject_label, record_list in records.items():
            subject = self.__project.add_subject(subject_label)

            for record in record_list:
                try:
                    subject.upload_acquisition_file(
                        session_label=self.__session_template.instantiate(
                            record),
                        acquisition_label=self.__acquisition_template.
                        instantiate(record),
                        filename=self.__filename_template.instantiate(record),
                        contents=json.dumps(record),
                        content_type='application/json')
                except SubjectError as error:
                    raise UploaderError(error) from error
                except ValueError as error:
                    raise UploaderError(error) from error

        return success


class FormJSONUploader(RecordUploader):

    def __init__(self, project: ProjectAdaptor, module: str) -> None:
        self.__project = project
        self.__module = module
        self.__pending_visits: Dict[str, VisitMapping] = {}

    def __add_pending_visit(self, *, subject: SubjectAdaptor, filename: str,
                            file_id: str, input_record: Dict[str, Any]):
        """Add the visit to the list of visits pending for QC for the
        participant.

        Args:
            subject: Flywheel subject adaptor for the participant
            filename: Flywheel aquisition file name
            file_id: Flywheel aquisition file ID
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

    def upload(self, participant_records: Dict[str, List[Dict[str,
                                                              Any]]]) -> bool:
        """Converts a tranformed CSV record to a JSON file and uploads it to
        the respective acquisition in Flywheel.

        - If the record already exists in Flywheel (duplicate), it will not be uploaded.
        - If the record is new/modified, upload it to Flywheel and update file metadata.

        Args:
            participant_visits: set of visits to upload, by participant

        Returns:
            bool: True if uploads are successful
        """

        success = True
        for subject_lbl, records in participant_records.items():
            subject = self.__project.find_subject(subject_lbl)
            if not subject:
                log.info(
                    'NACCID %s does not exist in project %s/%s, creating a new subject',
                    subject_lbl, self.__project.group, self.__project.label)
                subject = self.__project.add_subject(subject_lbl)

            for record in records:
                session_label = DefaultValues.SESSION_LBL_PRFX + \
                    record[FieldNames.VISITNUM]

                acq_label = record[FieldNames.MODULE].upper()

                visit_file_name = f'{subject_lbl}-{session_label}-{acq_label}.json'
                try:
                    new_file = subject.upload_acquisition_file(
                        session_label=session_label,
                        acquisition_label=acq_label,
                        filename=visit_file_name,
                        contents=json.dumps(record),
                        content_type='application/json')
                except (SubjectError, TypeError) as error:
                    log.error(error)
                    success = False
                    continue

                if not new_file:
                    continue

                if not update_file_info_metadata(new_file, record):
                    success = False
                    continue

                self.__add_pending_visit(subject=subject,
                                         filename=visit_file_name,
                                         file_id=new_file.id,
                                         input_record=record)

        success = success and self.__create_pending_visits_file()
        return success


class UploaderError(Exception):
    pass
