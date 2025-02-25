from typing import Literal, Optional

from fw_client.client import FWClient
from pydantic import BaseModel, Field, ValidationError

from flywheel_adaptor.flywheel_proxy import ProjectAdaptor


class Origin(BaseModel):
    """Defines origin object for project upsert request."""
    type: Literal['user', 'device', 'job', 'system', 'unknown', 'gear_rule']


class Source(BaseModel):
    """Defines source object for project upsert request."""
    type: Literal['device', 'user', 'import']
    id: str


class SubjectUpsertRequest(BaseModel):
    """Defines subject request object in project upsert.

    Note: pydantic hides fields with underscores, so exclude _id field.
    """
    label: str = Field('', max_length=64, min_length=1)


class SessionUpsertRequest(BaseModel):
    """Defines session request object in project upsert.

    Note: pydantic hides fields with underscores, so exclude _id field.
    """
    label: str = Field('', min_length=1)


class AcquisitionUpsertRequest(BaseModel):
    """Defines acquisition request object in project upsert.

    Note: pydantic hides fields with underscores, so exclude _id field.
    """
    label: str = Field('', min_length=1, max_length=128)


class ProjectHierarchyRequest(BaseModel):
    """Defines project hierarchy upsert request object."""
    origin: Origin
    source: Source
    subject: SubjectUpsertRequest
    session: SessionUpsertRequest
    acquisition: AcquisitionUpsertRequest


UpsertResult = Literal['created', 'updated', 'ignored', 'conflicts']


class SubjectUpsertResponse(BaseModel):
    """Defines subject response object for project hierarchy upsert."""
    id: str = Field(..., alias="_id")
    label: Optional[str] = None
    upsert_result: UpsertResult


class SessionUpsertResponse(BaseModel):
    """Defines session response object for project hierarchy upsert.

    Note: actual response includes _uid which is ignored by pydantic, but not used here.
    """
    id: str = Field(..., alias="_id")
    label: Optional[str] = None
    upsert_result: UpsertResult


class AcquisitionUpsertResponse(BaseModel):
    """Defines acquisition response object for project hierarchy upsert.

    Note: actual response includes _uid which is ignored by pydantic, but not used here.
    """
    id: str = Field(..., alias="_id")
    label: Optional[str] = None
    upsert_result: UpsertResult


class ProjectHierarchyResponse(BaseModel):
    """Defines response object for project hierarchy upsert operation."""
    subject: SubjectUpsertResponse
    session: Optional[SessionUpsertResponse] = None
    acquisition: Optional[AcquisitionUpsertResponse] = None


class SubjectHierarchy(BaseModel):
    """Defines class for subject/session/acquisition hierarchy."""
    subject_id: str
    session_id: str
    acquisition_id: str

    @classmethod
    def create(
        cls, project_hierarchy: ProjectHierarchyResponse
    ) -> Optional['SubjectHierarchy']:
        """Creates a subject hierarch object from the response of calling the
        project hierarchy-upsert endpoint.

        Args:
          project_hierarchy: response object
        Returns:
          SubjectHierarchy object with IDs for subject, session, acquisition.
          None if any of those values are missing or response indicates a conflict
          occurred.
        """
        if project_hierarchy.subject.upsert_result == 'conflicts':
            return None
        if not project_hierarchy.session:
            return None
        if project_hierarchy.session.upsert_result == 'conflicts':
            return None
        if not project_hierarchy.acquisition:
            return None
        if project_hierarchy.acquisition.upsert_result == 'conflicts':
            return None

        return SubjectHierarchy(
            subject_id=project_hierarchy.subject.id,
            session_id=project_hierarchy.session.id,
            acquisition_id=project_hierarchy.acquisition.id)


class HierarchyCreationClient:
    """Defines a FW client adaptor specifically for creating hierarchy
    containers in a project."""

    def __init__(self, device_key: str, device_id: str):
        self.__fw_client = FWClient(api_key=device_key)
        self.__device_id = device_id

    def create_hierarchy(self, project: ProjectAdaptor, subject_label: str,
                         session_label: str,
                         acquisition_label: str) -> Optional[SubjectHierarchy]:
        """Creates a subject-session-acquisition hierarchy within the project.

        Args:
          project_id: str
          subject_label: str
          session_label: str
          acquisition_label: str
        Returns:
          the subject hierarchy if successfully created. None, otherwise.
        """
        request = ProjectHierarchyRequest(
            origin=Origin(type='job'),
            source=Source(type='device', id=self.__device_id),
            subject=SubjectUpsertRequest(label=subject_label),
            session=SessionUpsertRequest(label=session_label),
            acquisition=AcquisitionUpsertRequest(label=acquisition_label))
        response = self.__fw_client.post(
            url=f"/api/projects/{project.id}/upsert-hierarchy",
            json=request.model_dump(exclude_none=True))

        try:
            result = ProjectHierarchyResponse.model_validate(response)
        except ValidationError:
            return None

        return SubjectHierarchy.create(result)
