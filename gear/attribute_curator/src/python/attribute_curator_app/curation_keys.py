# Keys/constants used for curation
from nacc_attribute_deriver.utils.scope import (
    FormScope,
    GeneticsScope,
    MixedProtocolScope,
)

# scopes that cover multiple visits and need cross-sectional derived variables
# back-propagated to each file. required for scopes that can have multiple
# visits/data and cross-sectional derived values
BACKPROP_SCOPES = [
    FormScope.UDS,
    FormScope.MILESTONE,
    MixedProtocolScope.MRI_DICOM,
    MixedProtocolScope.PET_DICOM,
]

# scopes with cross-sectional values that need to be
# pushed back into UDS/NP
CHILD_SCOPES = {
    FormScope.UDS: [
        FormScope.CROSS_MODULE,
        FormScope.MILESTONE,
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
}

# Scopes that need to write to file.info.resolved
# i.e. scopes that need file missingness applied
# ultimately this is probably just all form scopes
RESOLVED_SCOPES = [
    FormScope.UDS,
    FormScope.NP,
    FormScope.MDS,
    FormScope.CSF,
    FormScope.FTLD,
    FormScope.LBD,
    FormScope.CLS,
    FormScope.COVID_F1,
    FormScope.COVID_F2F3,
]


class FormCurationTags:
    """Class to store curation tags."""

    AFFILIATE = "affiliated"
    UDS_PARTICIPANT = "uds-participant"
