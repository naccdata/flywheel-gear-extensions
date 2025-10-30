"""Classes for NACC directory user credentials."""

import logging
from datetime import date
from typing import Any, Literal, Optional, get_args

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

from users.authorizations import (
    ActionType,
    DatatypeNameType,
    StudyAuthorizations,
)
from users.user_entry import ActiveUserEntry, PersonName, UserEntry

log = logging.getLogger(__name__)


AuthorizationAccessLevel = Literal["NoAccess", "ViewAccess", "SubmitAudit"]


def get_activity_prefix(
    access_level: AuthorizationAccessLevel,
) -> Optional[ActionType]:
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
            authorizations = StudyAuthorizations(study_id=study_id)
        action = get_activity_prefix(access_level)
        if action is not None:
            authorizations.add(datatype=datatype, action=action)
        self.access_level_map[study_id] = authorizations

    def get_authorizations(self) -> list[StudyAuthorizations]:
        """Returns the list of Authorizations objects from this study access
        map."""
        return list(self.access_level_map.values())


class DirectoryAuthorizations(BaseModel):
    """Data model for deserializing a json object from a directory permission
    report."""

    firstname: str
    lastname: str
    email: str
    auth_email: str = Field(alias="fw_email")
    inactive: bool = Field(alias="archive_contact")
    org_name: str = Field(alias="contact_company_name")
    adcid: int = Field(alias="adresearchctr")
    web_report_access: bool
    study_selections: list[str]
    adrc_enrollment_access_level: AuthorizationAccessLevel = Field(
        alias="p30_naccid_enroll_access_level"
    )
    adrc_form_access_level: AuthorizationAccessLevel = Field(
        alias="p30_clin_forms_access_level"
    )
    adrc_dicom_access_level: AuthorizationAccessLevel = Field(
        alias="p30_imaging_access_level"
    )
    ncrad_biomarker_access_level: AuthorizationAccessLevel = Field(
        alias="p30_flbm_access_level"
    )
    niagads_genetic_access_level: AuthorizationAccessLevel = Field(
        alias="p30_genetic_access_level"
    )
    affiliated_study: list[str]
    leads_enrollment_access_level: AuthorizationAccessLevel = Field(
        alias="leads_naccid_enroll_access_level"
    )
    leads_form_access_level: AuthorizationAccessLevel = Field(
        alias="leads_clin_forms_access_level"
    )
    dvcid_enrollment_access_level: AuthorizationAccessLevel = Field(
        alias="dvcid_naccid_enroll_access_level"
    )
    dvcid_form_access_level: AuthorizationAccessLevel = Field(
        alias="dvcid_clin_forms_access_level"
    )
    allftd_enrollment_access_level: AuthorizationAccessLevel = Field(
        alias="allftd_naccid_enroll_access_level"
    )
    allftd_form_access_level: AuthorizationAccessLevel = Field(
        alias="allftd_clin_forms_access_level"
    )
    dlbc_enrollment_access_level: AuthorizationAccessLevel = Field(
        alias="dlbc_naccid_enroll_access_level"
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
    adrc_scan_access_level: AuthorizationAccessLevel = Field(
        alias="scan_dashboard_access_level"
    )
    complete: bool = Field(alias="nacc_data_platform_access_information_complete")
    permissions_approval: bool
    permissions_approval_date: date
    permissions_approval_name: str

    @field_validator(
        "adrc_enrollment_access_level",
        "adrc_form_access_level",
        "adrc_dicom_access_level",
        "ncrad_biomarker_access_level",
        "niagads_genetic_access_level",
        "leads_enrollment_access_level",
        "leads_form_access_level",
        "dvcid_enrollment_access_level",
        "dvcid_form_access_level",
        "allftd_enrollment_access_level",
        "allftd_form_access_level",
        "dlbc_enrollment_access_level",
        "dlbc_form_access_level",
        "clariti_form_access_level",
        "clariti_dicom_access_level",
        "clariti_biomarker_access_level",
        "clariti_pay_access_level",
        "clariti_ror_access_level",
        "adrc_scan_access_level",
        mode="before",
    )
    def convert_access_level(cls, access_level: str) -> AuthorizationAccessLevel:
        if access_level == "ViewAccess":
            return "ViewAccess"
        if access_level == "SubmitAudit":
            return "SubmitAudit"

        return "NoAccess"

    @field_validator("study_selections", "affiliated_study", mode="before")
    def convert_string_list(cls, value_list: Any) -> list[str]:
        if isinstance(value_list, list):
            return value_list
        if not isinstance(value_list, str):
            raise TypeError("expecting string with list of values")

        return value_list.split(",")

    @field_validator(
        "web_report_access", "inactive", "permissions_approval", mode="before"
    )
    def convert_flag_string(cls, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if not isinstance(value, str):
            raise TypeError("expecting bool or string value")

        return value == "1"

    @field_validator("complete", mode="before")
    def convert_complete(cls, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if not isinstance(value, str):
            raise TypeError("expecting form completion value")

        return value == "2"

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
            datatype = "scan-analysis" if datatype == "scan" else datatype
            if datatype != "genetic" and datatype not in get_args(DatatypeNameType):
                log.warning("the data type %s is ignored for %s", datatype, self.email)
                continue

            datatypes = [(study, datatype)]
            if datatype == "genetic":
                datatypes = [
                    ("ncrad", "apoe"),
                    (study, "gwas"),
                    (study, "genetic-availability"),
                    (study, "imputation"),
                ]
            for datatype_t in datatypes:
                study_map.add(
                    study_id=datatype_t[0],
                    access_level=access_level,
                    datatype=datatype_t[1],  # type: ignore
                )

        return study_map

    def to_user_entry(self) -> Optional[UserEntry]:
        """Converts this DirectoryAuthorizations object to a UserEntry."""

        if not self.permissions_approval:
            return None
        if not self.complete:
            return None

        name = PersonName(first_name=self.firstname, last_name=self.lastname)
        email = self.email
        auth_email = self.auth_email if self.auth_email else self.email
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
