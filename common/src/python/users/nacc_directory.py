"""Classes for NACC directory user credentials."""

import logging
from datetime import date
from typing import Literal, Optional, get_args

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

from users.authorizations import (
    ActivityPrefixType,
    DatatypeNameType,
    StudyAuthorizations,
    convert_to_activity,
)
from users.user_entry import ActiveUserEntry, PersonName, UserEntry

log = logging.getLogger(__name__)


AuthorizationAccessLevel = Literal["NoAccess", "ViewAccess", "SubmitAudit"]


def get_activity_prefix(
    access_level: AuthorizationAccessLevel,
) -> Optional[ActivityPrefixType]:
    """Returns the activity prefix for the access level.

    Args:
      access_level: the access level
    Returns:
      the corresponding activity prefix if not NoAccess. Otherwise, None.
    """
    if access_level == "ViewAccess":
        return "view"
    if access_level == "SubmitAudit":
        return "submit-audit"

    return None


class StudyAccessMap(BaseModel):
    """Defines a data model for a map from study id to access level map
    objects.

    Used as an intermediate for computing the authorizations from a
    DirectoryAuthorizations object.
    """

    access_level_map: dict[str, StudyAuthorizations] = {}

    def add(
        self,
        study_id: str,
        access_level: AuthorizationAccessLevel,
        datatype: DatatypeNameType,
    ) -> None:
        """Adds the datatype to this map for the study id at the access level.

        Args:
          study_id: the study id
          access_level: the access level
          datatype: the datatype
        """
        authorizations = self.access_level_map.get(study_id)
        if authorizations is None:
            authorizations = StudyAuthorizations(study_id=study_id, activities=[])
        activity_prefix = get_activity_prefix(access_level)
        if activity_prefix is not None:
            authorizations.activities.append(
                convert_to_activity(activity_prefix=activity_prefix, datatype=datatype)
            )
        self.access_level_map[study_id] = authorizations

    def get_authorizations(self) -> list[StudyAuthorizations]:
        """Returns the list of Authorizations objects from this study access
        map."""
        return list(self.access_level_map.values())


class DirectoryAuthorizations(BaseModel):
    """Data model for deserializing a json object from a directory permission
    report."""

    record_id: int
    firstname: str
    lastname: str
    email: str
    auth_email: str = Field(alias="fw_email")
    inactive: bool = Field(alias="archive_contact")
    org_name: str = Field(alias="contact_company_name")
    adcid: int = Field(alias="adresearchctr")
    portal_access: bool = Field(alias="flywheel_access")
    adrc_enrollment_access_level: AuthorizationAccessLevel = Field(
        alias="naccid_enroll_access"
    )
    web_report_access_web: bool = Field(alias="web_report_access___web")
    web_report_access_repdash: bool = Field(alias="web_report_access___repdash")
    web_report_access_scandash: bool = Field(alias="web_report_access___scandash")
    study_selections_adrc: bool = Field(alias="study_selections___p30")
    study_selections_affiliatedstudy: bool = Field(
        alias="study_selections___affiliatedstudy"
    )
    adrc_form_access_level: AuthorizationAccessLevel = Field(
        alias="p30_clin_forms_access_level"
    )
    adrc_dicom_access_level: AuthorizationAccessLevel = Field(
        alias="p30_imaging_access_level"
    )
    adrc_biomarker_access_level: AuthorizationAccessLevel = Field(
        alias="p30_flbm_access_level"
    )
    adrc_genetic_access_level: AuthorizationAccessLevel = Field(
        alias="p30_genetic_access_level"
    )
    affiliated_study_leads: bool = Field(alias="affiliated_study___leads")
    affiliated_study_dvcid: bool = Field(alias="affiliated_study___dvcid")
    affiliated_study_allftd: bool = Field(alias="affiliated_study___allftd")
    affiliated_study_dlbc: bool = Field(alias="affiliated_study___dlbc")
    affiliated_study_clariti: bool = Field(alias="affiliated_study___clariti")
    leads_form_access_level: AuthorizationAccessLevel = Field(
        alias="leads_clin_forms_access_level"
    )
    dvcid_form_access_level: AuthorizationAccessLevel = Field(
        alias="dvcid_clin_forms_access_level"
    )
    allftd_form_access_level: AuthorizationAccessLevel = Field(
        alias="allftd_clin_forms_access_level"
    )
    dlbc_form_access_level: AuthorizationAccessLevel = Field(
        alias="dlbc_clin_forms_access_level"
    )
    clariti_form_access_level: AuthorizationAccessLevel = Field(
        alias="cl_clin_forms_access_level"
    )
    clariti_dicom_access_level: AuthorizationAccessLevel = Field(
        alias="cl_imaging_access_level"
    )
    clariti_biomarker_access_level: AuthorizationAccessLevel = Field(
        alias="cl_flbm_access_level"
    )
    clariti_pay_access_level: AuthorizationAccessLevel = Field(
        alias="cl_pay_access_level"
    )
    clariti_ror_access_level: AuthorizationAccessLevel = Field(
        alias="cl_ror_access_level"
    )
    permissions_approval: bool
    permissions_approval_date: date

    @field_validator(
        "adrc_enrollment_access_level",
        "adrc_form_access_level",
        "adrc_dicom_access_level",
        "adrc_biomarker_access_level",
        "adrc_genetic_access_level",
        "leads_form_access_level",
        "dvcid_form_access_level",
        "allftd_form_access_level",
        "dlbc_form_access_level",
        "clariti_form_access_level",
        "clariti_dicom_access_level",
        "clariti_biomarker_access_level",
        "clariti_pay_access_level",
        "clariti_ror_access_level",
        mode="before",
    )
    def convert_access_level(cls, access_level: str) -> AuthorizationAccessLevel:
        if access_level == "ViewAccess":
            return "ViewAccess"
        if access_level == "SubmitAudit":
            return "SubmitAudit"

        return "NoAccess"

    def __parse_fields(self) -> StudyAccessMap:
        """Parses the fields of this object for access level permissions and
        constructs a mapping study -> access-level -> datatypes.

        Returns:
          the mapping of study and access level to datatype
        """
        study_map = StudyAccessMap()
        field_names = DirectoryAuthorizations.model_fields.keys()
        for field_name in field_names:
            if not field_name.endswith("_access_level"):
                continue

            access_level = getattr(self, field_name)
            if access_level == "NoAccess":
                continue

            temp_list = field_name.split("_")
            if len(temp_list) != 4:
                continue
            study, datatype, *tail = temp_list
            if datatype not in get_args(DatatypeNameType):
                log.warning(
                    "the data type %s is ignored for %s %s",
                    datatype,
                    self.firstname,
                    self.lastname,
                )
                continue

            study_map.add(study_id=study, access_level=access_level, datatype=datatype)  # type: ignore
        return study_map

    def to_user_entry(self) -> Optional[UserEntry]:
        """Converts this DirectoryAuthorizations object to a UserEntry."""
        if not self.portal_access:
            return None
        if not self.permissions_approval:
            return None

        name = PersonName(first_name=self.firstname, last_name=self.lastname)
        email = self.email
        auth_email = self.auth_email
        if self.inactive:
            return UserEntry(
                name=name,
                email=email,
                auth_email=auth_email,
                active=False,
                approved=self.permissions_approval,
            )

        authorizations = self.__parse_fields().get_authorizations()
        return ActiveUserEntry(
            org_name=self.org_name,
            adcid=int(self.adcid),
            name=name,
            email=email,
            auth_email=auth_email,
            authorizations=authorizations,
            active=True,
            approved=self.permissions_approval,
        )
