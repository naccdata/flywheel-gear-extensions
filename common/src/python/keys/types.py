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
    "scan-analysis",
]

PipelineStageType = Literal[
    "ingest", "retrospective", "sandbox", "distribution", "accepted"
]
