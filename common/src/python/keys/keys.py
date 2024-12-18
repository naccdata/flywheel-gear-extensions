"""Frquently accessed field names, labels, and default values."""


class FieldNames:
    """Class to store frquently accessed field names."""
    NACCID = 'naccid'
    MODULE = 'module'
    PACKET = 'packet'
    PTID = 'ptid'
    ADCID = 'adcid'
    MODE = 'mode'
    VISITNUM = 'visitnum'
    DATE_COLUMN = 'visitdate'
    FORMVER = 'formver'
    GUID = 'guid'
    OLDADCID = 'oldadcid'
    OLDPTID = 'oldptid'
    ENRLFRM_DATE = 'frmdate_enrl'
    ENRLFRM_INITL = 'initials_enrl'
    NACCIDKWN = 'naccidknwn'
    PREVENRL = 'prevenrl'
    C2C2T = 'rmmodec2c2t'


class RuleLabels:
    """Class to store rule definition labels."""
    CODE = 'code'
    INDEX = 'index'
    COMPAT = 'compatibility'
    TEMPORAL = 'temporalrules'
    NULLABLE = 'nullable'
    REQUIRED = 'required'
    GDS = 'compute_gds'


class DefaultValues:
    """Class to store default values."""
    NOTFILLED = 0
    LEGACY_PRJ_LABEL = 'retrospective-form'
    ENROLLMENT_MODULE = 'ENROLL'
    UDS_MODULE = 'UDS'
    GEARBOT_USER_ID = 'nacc-flywheel-gear@uw.edu'
    NACC_GROUP_ID = 'nacc'
    METADATA_PRJ_LBL = 'metadata'
    ADMIN_PROJECT = 'project-admin'
    SESSION_LBL_PRFX = 'FORMS-VISIT-'
    ENRL_SESSION_LBL_PRFX = 'ENROLLMENT-TRANSFER-'
    C2TMODE = 1
    LBD_SHORT_VER = 3.1
    QC_JSON_DIR = 'JSON'
    QC_GEAR = 'form-qc-checker'
    LEGACY_QC_GEAR = 'file-validator'
    MAX_POOL_CONNECTIONS = 50


class MetadataKeys:
    """Class to store metadata keys."""
    LEGACY_KEY = 'legacy'
    LEGACY_LBL = 'legacy_label'
    LEGACY_ORDERBY = 'legacy_orderby'
    FAILED = 'failed'
    C2 = 'UDS-C2'
    C2T = 'UDS-C2T'
    LBD_LONG = 'LBD-v3.0'
    LBD_SHORT = 'LBD-v3.1'
