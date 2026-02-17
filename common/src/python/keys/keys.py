"""Frequently accessed field names, labels, and default values."""

REDCapKeys = ["redcap_event_name", "redcap_repeat_instance", "redcap_repeat_instrument"]


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
    ENRL_PRJ_LABEL = "ingest-enrollment"
    FORM_PRJ_LABEL = "ingest-form"
    ENROLLMENT_MODULE = "ENROLL"
    UDS_MODULE = "UDS"
    MDS_MODULE = "MDS"
    BDS_MODULE = "BDS"
    NP_MODULE = "NP"
    MLST_MODULE = "MLST"
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
    PROVISIONING_GEAR = "identifier-provisioning"
    MAX_POOL_CONNECTIONS = 50
    PROV_SUFFIX = "provisioning"
    IDENTIFIER_SUFFIX = "identifiers"
    FW_SEARCH_OR = "=|"
    UDS_I_PACKET = "I"
    UDS_IT_PACKET = "IT"
    UDS_I4_PACKET = "I4"
    UDS_F_PACKET = "F"
    UDS_T_PACKET = "T"
    SUBMISSION_PIPELINE = "submission"
    FINALIZATION_PIPELINE = "finalization"
    FINALIZED_TAG = "submission-completed"
    MODULE_PATTERN = "a-zA-Z1-9_"


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
    CLINICAL_FORM_REQUIRED_MLST = "preprocess-005"
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
    CLINICAL_FORM_REQUIRED_NP = "preprocess-025"
    DEATH_DENOTED_ON_MLST = "preprocess-026"
    NP_MLST_DOD_MISMATCH = "preprocess-027"
    LOWER_NP_DOD = "preprocess-028"
    NP_UDS_SEX_MISMATCH = "preprocess-029"
    NP_UDS_DAGE_MISMATCH = "preprocess-030"
    UDS_NOT_EXIST = "preprocess-031"

    # other errors for preprocessing issues that don't fall
    # in above categories
    PREPROCESSING_ERROR = "preprocess-error"
    CLINICAL_FORM_REQUIRED = "preprocess-101"


class PreprocessingChecks:
    DUPLICATE_RECORD = "duplicate-record"
    VERSION = "version"
    PACKET = "packet"
    OPTIONAL_FORMS = "optional-forms"
    SUPPLEMENT_MODULE = "supplement-module"
    IVP = "ivp"
    UDSV4_IVP = "udsv4-ivp"
    VISIT_CONFLICT = "visit-conflict"
    CLINICAL_FORMS = "clinical-forms"
    NP_MLST_RESTRICTIONS = "np-mlst-restrictions"
    NP_UDS_RESTRICTIONS = "np-uds-restrictions"

    @classmethod
    def is_check_defined(cls, check: str) -> bool:
        class_variables = vars(PreprocessingChecks)
        return check in class_variables.values()
