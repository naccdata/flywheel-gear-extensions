from typing import Literal

DatatypeNameType = Literal[
    "apoe",
    "biomarker",
    "data-freeze",
    "dicom",
    "enrollment",
    "form",
    "genetic-availability",
    "gwas",
    "imputation",
    "participant-summary",
    "scan-analysis",
]

PipelineStageType = Literal[
    "ingest", "retrospective", "sandbox", "distribution", "accepted"
]
