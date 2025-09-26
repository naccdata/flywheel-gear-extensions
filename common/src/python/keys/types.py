from typing import Literal

DatatypeNameType = Literal[
    "apoe",
    "biomarker",
    "dicom",
    "enrollment",
    "form",
    "genetic-availability",
    "gwas",
    "imputation",
]
ModuleName = Literal["UDS", "FTLD", "LBD", "MDS"]
PipelineStageType = Literal[
    "ingest", "retrospective", "sandbox", "distribution", "accepted"
]
