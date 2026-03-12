"""Classes for NACC directory user credentials."""

import logging
from datetime import date
from typing import Any, Literal, Optional, get_args

from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    field_validator,
)

from users.authorizations import (
    ActionType,
    Authorizations,
    DashboardResource,
    DatatypeNameType,
    DatatypeResource,
    PageResource,
    Resource,
    StudyAuthorizations,
)
from users.clariti_roles import map_clariti_roles_to_activities
from users.user_entry import ActiveUserEntry, CenterUserEntry, PersonName, UserEntry

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

    study_access_level_map: dict[str, StudyAuthorizations] = {}
    general_authorizations: Authorizations = Authorizations()

    def add_study_access(
        self,
        study_id: str,
        access_level: AuthorizationAccessLevel,
        resource: Resource,
    ) -> None:
        """Adds the resource to this map for the study id at the access level.

        Args:
          study_id: the study id
          access_level: the access level
          resource: the resource (DatatypeResource, DashboardResource, etc.)
        """
        authorizations = self.study_access_level_map.get(study_id)
        if authorizations is None:
            authorizations = StudyAuthorizations(study_id=study_id)
        action = get_activity_prefix(access_level)
        if action is not None:
            authorizations.add(resource=resource, action=action)
        self.study_access_level_map[study_id] = authorizations

    def add_general_access(
        self, access_level: AuthorizationAccessLevel, resource: Resource
    ) -> None:
        """Adds the resource to general authorizations at the access level.

        Args:
          access_level: the access level
          resource: the resource (PageResource, DashboardResource, etc.)
        """
        action = get_activity_prefix(access_level)
        if action is not None:
            self.general_authorizations.add(resource=resource, action=action)

    def get_authorizations(self) -> Authorizations:
        return self.general_authorizations

    def get_study_authorizations(self) -> list[StudyAuthorizations]:
        """Returns the list of Authorizations objects from this study access
        map."""
        return list(self.study_access_level_map.values())


class DirectoryAuthorizations(BaseModel):
    """Data model for deserializing a json object from a directory permission
    report.

    Note: general_page_community_resources_access_level and
    adrc_dashboard_reports_access_level both use the same source field
    (web_report_access) for deserialization. This model is only used for
    deserialization from REDCap reports and is never serialized.
    """

    firstname: str
    lastname: str
    email: str
    auth_email: str = Field(alias="fw_email")
    inactive: bool = Field(alias="archive_contact")
    org_name: str = Field(alias="contact_company_name")
    adcid: Optional[int] = Field(alias="adcid")
    general_page_community_resources_access_level: AuthorizationAccessLevel = Field(
        validation_alias=AliasChoices("web_report_access")
    )
    adrc_dashboard_reports_access_level: AuthorizationAccessLevel = Field(
        validation_alias=AliasChoices("web_report_access")
    )
    study_selections: list[str]
    adrc_datatype_enrollment_access_level: AuthorizationAccessLevel = Field(
        alias="p30_naccid_enroll_access_level"
    )
    adrc_datatype_form_access_level: AuthorizationAccessLevel = Field(
        alias="p30_clin_forms_access_level"
    )
    adrc_datatype_dicom_access_level: AuthorizationAccessLevel = Field(
        alias="p30_imaging_access_level"
    )
    ncrad_datatype_biomarker_access_level: AuthorizationAccessLevel = Field(
        alias="p30_flbm_access_level"
    )
    niagads_datatype_genetic_access_level: AuthorizationAccessLevel = Field(
        alias="p30_genetic_access_level"
    )
    affiliated_study: list[str]
    leads_datatype_enrollment_access_level: AuthorizationAccessLevel = Field(
        alias="leads_naccid_enroll_access_level"
    )
    leads_datatype_form_access_level: AuthorizationAccessLevel = Field(
        alias="leads_clin_forms_access_level"
    )
    dvcid_datatype_enrollment_access_level: AuthorizationAccessLevel = Field(
        alias="dvcid_naccid_enroll_access_level"
    )
    dvcid_datatype_form_access_level: AuthorizationAccessLevel = Field(
        alias="dvcid_clin_forms_access_level"
    )
    allftd_datatype_enrollment_access_level: AuthorizationAccessLevel = Field(
        alias="allftd_naccid_enroll_access_level"
    )
    allftd_datatype_form_access_level: AuthorizationAccessLevel = Field(
        alias="allftd_clin_forms_access_level"
    )
    dlbc_datatype_enrollment_access_level: AuthorizationAccessLevel = Field(
        alias="dlbc_naccid_enroll_access_level"
    )
    dlbc_datatype_form_access_level: AuthorizationAccessLevel = Field(
        alias="dlbc_clin_forms_access_level"
    )
    clariti_datatype_form_access_level: AuthorizationAccessLevel = Field(
        alias="cl_clin_forms_access_level"
    )
    clariti_datatype_dicom_access_level: AuthorizationAccessLevel = Field(
        alias="cl_imaging_access_level"
    )
    clariti_datatype_biomarker_access_level: AuthorizationAccessLevel = Field(
        alias="cl_flbm_access_level"
    )
    clariti_dashboard_pay_access_level: AuthorizationAccessLevel = Field(
        alias="cl_pay_access_level"
    )
    clariti_datatype_participant_summary_access_level: AuthorizationAccessLevel = Field(
        alias="cl_ror_access_level"
    )
    adrc_datatype_scan_analysis_access_level: AuthorizationAccessLevel = Field(
        alias="scan_dashboard_access_level"
    )
    # CLARiTI organizational roles (14 fields)
    loc_clariti_role___u01copi: Optional[bool] = Field(
        default=None, alias="loc_clariti_role___u01copi"
    )
    loc_clariti_role___pi: Optional[bool] = Field(
        default=None, alias="loc_clariti_role___pi"
    )
    loc_clariti_role___piadmin: Optional[bool] = Field(
        default=None, alias="loc_clariti_role___piadmin"
    )
    loc_clariti_role___copi: Optional[bool] = Field(
        default=None, alias="loc_clariti_role___copi"
    )
    loc_clariti_role___subawardadmin: Optional[bool] = Field(
        default=None, alias="loc_clariti_role___subawardadmin"
    )
    loc_clariti_role___addlsubaward: Optional[bool] = Field(
        default=None, alias="loc_clariti_role___addlsubaward"
    )
    loc_clariti_role___studycoord: Optional[bool] = Field(
        default=None, alias="loc_clariti_role___studycoord"
    )
    loc_clariti_role___mpi: Optional[bool] = Field(
        default=None, alias="loc_clariti_role___mpi"
    )
    loc_clariti_role___orecore: Optional[bool] = Field(
        default=None, alias="loc_clariti_role___orecore"
    )
    loc_clariti_role___crl: Optional[bool] = Field(
        default=None, alias="loc_clariti_role___crl"
    )
    loc_clariti_role___advancedmri: Optional[bool] = Field(
        default=None, alias="loc_clariti_role___advancedmri"
    )
    loc_clariti_role___physicist: Optional[bool] = Field(
        default=None, alias="loc_clariti_role___physicist"
    )
    loc_clariti_role___addlimaging: Optional[bool] = Field(
        default=None, alias="loc_clariti_role___addlimaging"
    )
    loc_clariti_role___reg: Optional[bool] = Field(
        default=None, alias="loc_clariti_role___reg"
    )
    # CLARiTI individual role (1 field)
    ind_clar_core_role___admin: Optional[bool] = Field(
        default=None, alias="ind_clar_core_role___admin"
    )
    permissions_approval: bool
    permissions_approval_date: date
    permissions_approval_name: str

    @field_validator("firstname", "lastname", mode="before")
    def strip_names(cls, value: Any) -> str:
        """Strip leading and trailing whitespace from names.

        Prevents trailing spaces from REDCap data from causing issues with
        name matching in COManage registry and Flywheel.

        Args:
            value: the name value to strip

        Returns:
            the name with leading and trailing whitespace removed
        """
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("adcid", mode="before")
    def convert_adcid(cls, adcid: Any) -> Optional[int]:
        if isinstance(adcid, int):
            return adcid
        if not isinstance(adcid, str):
            return adcid

        # Handle empty strings and non-numeric values
        if not adcid or adcid.strip() == "" or adcid.upper() == "NA":
            return None

        try:
            return int(adcid)
        except ValueError:
            return None

    @field_validator(
        "loc_clariti_role___u01copi",
        "loc_clariti_role___pi",
        "loc_clariti_role___piadmin",
        "loc_clariti_role___copi",
        "loc_clariti_role___subawardadmin",
        "loc_clariti_role___addlsubaward",
        "loc_clariti_role___studycoord",
        "loc_clariti_role___mpi",
        "loc_clariti_role___orecore",
        "loc_clariti_role___crl",
        "loc_clariti_role___advancedmri",
        "loc_clariti_role___physicist",
        "loc_clariti_role___addlimaging",
        "loc_clariti_role___reg",
        "ind_clar_core_role___admin",
        mode="before",
    )
    def convert_clariti_checkbox(cls, value: Any) -> Optional[bool]:
        """Convert REDCap checkbox values to boolean.

        REDCap checkboxes: "1" = checked, "0" or "" = unchecked.
        Returns True for "1", None for "0", "", or None.
        Boolean values pass through unchanged.
        """
        if value is None or value == "" or value == "0":
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value == "1":
            return True
        return None

    @field_validator(
        "adrc_datatype_enrollment_access_level",
        "adrc_datatype_form_access_level",
        "adrc_datatype_dicom_access_level",
        "ncrad_datatype_biomarker_access_level",
        "niagads_datatype_genetic_access_level",
        "leads_datatype_enrollment_access_level",
        "leads_datatype_form_access_level",
        "dvcid_datatype_enrollment_access_level",
        "dvcid_datatype_form_access_level",
        "allftd_datatype_enrollment_access_level",
        "allftd_datatype_form_access_level",
        "dlbc_datatype_enrollment_access_level",
        "dlbc_datatype_form_access_level",
        "clariti_datatype_form_access_level",
        "clariti_datatype_dicom_access_level",
        "clariti_datatype_biomarker_access_level",
        "clariti_dashboard_pay_access_level",
        "clariti_datatype_participant_summary_access_level",
        "adrc_datatype_scan_analysis_access_level",
        mode="before",
    )
    def convert_access_level(cls, access_level: str) -> AuthorizationAccessLevel:
        if access_level == "ViewAccess":
            return "ViewAccess"
        if access_level == "SubmitAudit":
            return "SubmitAudit"

        return "NoAccess"

    @field_validator("general_page_community_resources_access_level", mode="before")
    def convert_community_resources_access_level(
        cls, value: Any
    ) -> AuthorizationAccessLevel:
        """Converts web_report_access checkbox field to community resources
        access level.

        The field can contain: '', 'Web', 'RepDash', or 'Web,RepDash'.
        Returns ViewAccess if 'Web' is present, otherwise NoAccess.
        """
        if isinstance(value, str) and "Web" in value:
            return "ViewAccess"
        return "NoAccess"

    @field_validator("adrc_dashboard_reports_access_level", mode="before")
    def convert_adrc_reports_access_level(cls, value: Any) -> AuthorizationAccessLevel:
        """Converts web_report_access checkbox field to ADRC Reports access
        level.

        The field can contain: '', 'Web', 'RepDash', or 'Web,RepDash'.
        Returns ViewAccess if 'RepDash' is present, otherwise NoAccess.
        """
        if isinstance(value, str) and "RepDash" in value:
            return "ViewAccess"
        return "NoAccess"

    @field_validator("study_selections", "affiliated_study", mode="before")
    def convert_string_list(cls, value_list: Any) -> list[str]:
        if isinstance(value_list, list):
            return value_list
        if not isinstance(value_list, str):
            raise TypeError("expecting string with list of values")

        return value_list.split(",")

    @field_validator("inactive", "permissions_approval", mode="before")
    def convert_flag_string(cls, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if not isinstance(value, str):
            raise TypeError("expecting bool or string value")

        return value == "1"

    def __handle_datatype_resource(
        self,
        study_map: StudyAccessMap,
        scope: str,
        resource_name: str,
        access_level: AuthorizationAccessLevel,
    ) -> None:
        """Handle datatype resource parsing and addition to study map."""
        # Validate datatype
        if resource_name != "genetic" and resource_name not in get_args(
            DatatypeNameType
        ):
            log.warning(
                "the data type %s is ignored for %s",
                resource_name,
                self.email,
            )
            return

        # Handle genetic datatype expansion
        if resource_name == "genetic":
            # Genetic expands to multiple datatypes across studies
            study_map.add_study_access(
                study_id="ncrad",
                access_level=access_level,
                resource=DatatypeResource(datatype="apoe"),
            )
            study_map.add_study_access(
                study_id=scope,
                access_level=access_level,
                resource=DatatypeResource(datatype="gwas"),
            )
            study_map.add_study_access(
                study_id=scope,
                access_level=access_level,
                resource=DatatypeResource(datatype="genetic-availability"),
            )
            study_map.add_study_access(
                study_id=scope,
                access_level=access_level,
                resource=DatatypeResource(datatype="imputation"),
            )
        else:
            study_map.add_study_access(
                study_id=scope,
                access_level=access_level,
                resource=DatatypeResource(datatype=resource_name),  # type: ignore
            )

    def __handle_page_resource(
        self,
        study_map: StudyAccessMap,
        scope: str,
        resource_name: str,
        access_level: AuthorizationAccessLevel,
    ) -> None:
        """Handle page resource parsing and addition to study map."""
        resource = PageResource(page=resource_name)
        if scope == "general":
            study_map.add_general_access(access_level=access_level, resource=resource)
        else:
            study_map.add_study_access(
                study_id=scope, access_level=access_level, resource=resource
            )

    def __handle_dashboard_resource(
        self,
        study_map: StudyAccessMap,
        scope: str,
        resource_name: str,
        access_level: AuthorizationAccessLevel,
    ) -> None:
        """Handle dashboard resource parsing and addition to study map."""
        resource = DashboardResource(dashboard=resource_name)
        if scope == "general":
            study_map.add_general_access(access_level=access_level, resource=resource)
        else:
            study_map.add_study_access(
                study_id=scope, access_level=access_level, resource=resource
            )

    def __parse_fields(self) -> StudyAccessMap:
        """Parses the fields of this object for access level permissions and
        constructs a mapping study -> access-level -> resources.

        Field pattern: {scope}_{resource_type}_{resource_name}_access_level
        - scope: study ID (e.g., "adrc", "clariti") or "general"
        - resource_type: "datatype", "dashboard", or "page"
        - resource_name: one or more tokens converted to kabob-case
        - suffix: "_access_level"

        Returns:
          the mapping of study and access level to resource
        """
        study_map = StudyAccessMap()
        field_names = DirectoryAuthorizations.model_fields.keys()
        for field_name in field_names:
            if not field_name.endswith("_access_level"):
                continue

            access_level = getattr(self, field_name)
            if access_level == "NoAccess":
                continue

            # Parse field name: {scope}_{resource_type}_{resource_name}_access_level
            tokens = field_name.split("_")
            # Remove "access" and "level" from end
            if len(tokens) < 4 or tokens[-2:] != ["access", "level"]:
                continue
            tokens = tokens[:-2]

            # Must have at least scope, resource_type, and resource_name
            if len(tokens) < 3:
                continue

            scope = tokens[0]
            resource_type = tokens[1]
            resource_name_parts = tokens[2:]
            resource_name = "-".join(resource_name_parts)

            # Handle different resource types
            if resource_type == "datatype":
                self.__handle_datatype_resource(
                    study_map, scope, resource_name, access_level
                )
                continue

            if resource_type == "page":
                self.__handle_page_resource(
                    study_map, scope, resource_name, access_level
                )
                continue

            if resource_type == "dashboard":
                self.__handle_dashboard_resource(
                    study_map, scope, resource_name, access_level
                )
                continue

            log.warning("unknown resource type %s for %s", resource_type, self.email)

        # Add CLARiTI role-based activities
        clariti_activities = map_clariti_roles_to_activities(self)
        for activity in clariti_activities:
            study_map.add_study_access(
                study_id="clariti",
                access_level="ViewAccess",
                resource=activity.resource,
            )

        return study_map

    def to_user_entry(self) -> Optional[UserEntry]:
        """Converts this DirectoryAuthorizations object to a UserEntry."""

        if not self.permissions_approval:
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
        if self.adcid is None:
            return ActiveUserEntry(
                name=name,
                email=email,
                auth_email=auth_email,
                active=True,
                approved=self.permissions_approval,
                authorizations=authorizations,
            )

        study_authorizations = self.__parse_fields().get_study_authorizations()
        return CenterUserEntry(
            org_name=self.org_name,
            adcid=int(self.adcid),
            name=name,
            email=email,
            auth_email=auth_email,
            authorizations=authorizations,
            study_authorizations=study_authorizations,
            active=True,
            approved=self.permissions_approval,
        )
