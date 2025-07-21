"""Frequently accessed field names, labels, and default values."""

REDCapKeys = ["redcap_event_name", "redcap_repeat_instance", "redcap_repeat_instrument"]


class FieldNames:
    """Class to store frequently accessed field names."""

    NACCID = "naccid"
    MODULE = "module"
    PACKET = "packet"
    PTID = "ptid"
    ADCID = "adcid"
    MODE = "mode"
    VISITNUM = "visitnum"
    DATE_COLUMN = "visitdate"
    FORMVER = "formver"
    GUID = "guid"
    OLDADCID = "oldadcid"
    OLDPTID = "oldptid"
    ENRLFRM_DATE = "frmdate_enrl"
    ENRLFRM_INITL = "initials_enrl"
    NACCIDKWN = "naccidknwn"
    PREVENRL = "prevenrl"
    C2C2T = "rmmodec2c2t"
    ENRLTYPE = "enrltype"
    GUIDAVAIL = "guidavail"


class RuleLabels:
    """Class to store rule definition labels."""

    CODE = "code"
    INDEX = "index"
    COMPAT = "compatibility"
    TEMPORAL = "temporalrules"
    NULLABLE = "nullable"
    REQUIRED = "required"
    GDS = "compute_gds"


class DefaultValues:
    """Class to store default values."""

    PRIMARY_STUDY = "adrc"
    NOTFILLED = 0
    LEGACY_PRJ_LABEL = "retrospective-form"
    ENROLLMENT_MODULE = "ENROLL"
    UDS_MODULE = "UDS"
    MDS_MODULE = "MDS"
    BDS_MODULE = "BDS"
    GEARBOT_USER_ID = "nacc-flywheel-gear@uw.edu"
    NACC_GROUP_ID = "nacc"
    METADATA_PRJ_LBL = "metadata"
    ACCEPTED_PRJ_LBL = "accepted"
    ADMIN_PROJECT = "project-admin"
    SESSION_LBL_PRFX = "FORMS-VISIT-"
    ENRL_SESSION_LBL_PRFX = "ENROLLMENT-TRANSFER-"
    C2TMODE = 1
    LBD_SHORT_VER = 3.1
    QC_JSON_DIR = "JSON"
    QC_GEAR = "form-qc-checker"
    LEGACY_QC_GEAR = "file-validator"
    MAX_POOL_CONNECTIONS = 50
    PROV_SUFFIX = "provisioning"
    IDENTIFIER_SUFFIX = "identifiers"
    FW_SEARCH_OR = "=|"
    UDS_I_PACKET = "I"
    UDS_IT_PACKET = "IT"
    UDS_I4_PACKET = "I4"
    UDS_F_PACKET = "F"
    SUBMISSION_PIPELINE = "submission"
    FINALIZATION_PIPELINE = "finalization"
    FINALIZED_TAG = "submission-completed"


class MetadataKeys:
    """Class to store metadata keys."""

    LEGACY_KEY = "legacy"
    LEGACY_LBL = "legacy_label"
    LEGACY_ORDERBY = "legacy_orderby"
    FAILED = "failed"
    C2 = "UDS-C2"
    C2T = "UDS-C2T"
    LBD_LONG = "LBD-v3.0"
    LBD_SHORT = "LBD-v3.1"
    TRANSFERS = "transfers"
    MODULE_CONFIGS = "module_configs"
    FORM_METADATA_PATH = "file.info.forms.json"
    VALIDATED_TIMESTAMP = "validated-timestamp"
    TRIGGERED_TIMESTAMP = "triggered-timestamp"

    @classmethod
    def get_column_key(cls, column: str) -> str:
        return f"{cls.FORM_METADATA_PATH}.{column}"


class SysErrorCodes:
    """Class to store pre-processing error codes."""

    ADCID_MISMATCH = "preprocess-001"
    IVP_EXISTS = "preprocess-002"
    UDS_NOT_MATCH = "preprocess-003"
    INVALID_MODULE_PACKET = "preprocess-004"
    UDS_NOT_EXIST = "preprocess-005"
    DIFF_VISITDATE = "preprocess-006"
    DIFF_VISITNUM = "preprocess-007"
    LOWER_FVP_VISITNUM = "preprocess-008"
    LOWER_I4_VISITNUM = "preprocess-009"
    LOWER_FVP_VISITDATE = "preprocess-010"
    LOWER_I4_VISITDATE = "preprocess-011"
    EXCLUDED_FIELDS = "preprocess-012"
    INVALID_PACKET = "preprocess-013"
    INVALID_VERSION = "preprocess-014"
    INVALID_PTID = "preprocess-015"
    INVALID_MODULE = "preprocess-016"
    MISSING_IVP = "preprocess-017"
    MULTIPLE_IVP = "preprocess-018"
    UDS_NOT_APPROVED = "preprocess-019"
    MISSING_UDS_V3 = "preprocess-020"
    MISSING_UDS_I4 = "preprocess-021"
    DUPLICATE_VISIT = "preprocess-022"
    LOWER_VISITNUM = "preprocess-023"
    MISSING_SUBMISSION_STATUS = "preprocess-024"


class PreprocessingChecks:
    DUPLICATE_RECORD = "duplicate-record"
    VERSION = "version"
    PACKET = "packet"
    OPTIONAL_FORMS = "optional-forms"
    SUPPLEMENT_MODULE = "supplement-module"
    IVP = "ivp"
    UDSV4_IVP = "udsv4-ivp"
    VISIT_CONFLICT = "visit-conflict"
