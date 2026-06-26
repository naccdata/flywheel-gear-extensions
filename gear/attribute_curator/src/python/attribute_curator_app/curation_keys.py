# Keys/constants used for curation
from nacc_attribute_deriver.utils.scope import (
    FormScope,
    GeneticsScope,
    MixedProtocolScope,
)

# Scopes that need back-propagation applied to it. This ensures cross-sectional
# variables are applied to all files in the scope (e.g. pushed back longitudinally)
# In the case of UDS/NP/MLST, they share the cross-module variables, and need those
#   variables to also be added to the scope
# In the case of UDS, it has multiple other scopes pushed into it, since it is
#   generally the source/holder of all derived variables particularly in regards
#   to the RDD/QAF

# This is largely done due to the fact that the ETL is limited and cannot pull from
# multiple sources (e.g. subject AND file levels), so the variables need to exist
# at the file level to be picked up
BACKPROP_SCOPES = {
    FormScope.UDS: [
        FormScope.CROSS_MODULE,
        FormScope.FTLD,
        FormScope.LBD,
        FormScope.CSF,
        GeneticsScope.APOE,
        GeneticsScope.NCRAD_BIOSAMPLES,
        GeneticsScope.NIAGADS_AVAILABILITY,
        MixedProtocolScope.MRI_DICOM,
        MixedProtocolScope.PET_DICOM,
    ],
    FormScope.NP: [FormScope.CROSS_MODULE],
    FormScope.MLST: [FormScope.CROSS_MODULE],
    MixedProtocolScope.MRI_DICOM: [],
    MixedProtocolScope.PET_DICOM: [],
}

# Scopes that need to write to file.info.resolved
# i.e. scopes that need file missingness applied
# ultimately this is probably just all form scopes
RESOLVED_SCOPES = [
    FormScope.UDS,
    FormScope.NP,
    FormScope.MDS,
    FormScope.MLST,
    FormScope.CSF,
    FormScope.FTLD,
    FormScope.LBD,
    FormScope.DS,
    FormScope.CLS,
    FormScope.COVID,
    FormScope.BDS,
]


class FormCurationTags:
    """Class to store curation tags."""

    AFFILIATE = "affiliated"
    UDS_PARTICIPANT = "uds-participant"
