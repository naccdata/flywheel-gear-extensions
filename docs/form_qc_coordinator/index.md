# Form QC Coordinator

This gear coordinates the data quality checks for a given participant. It internally triggers the [Form QC Checker](../form_qc_checker/index.md) gear to validate each visit.
- Visits are evaluated in the order of the visit date. 
- If a visit fails validation, none of the subsequent visits will be evaluated until the failed visit is fixed.
- If a visit is modified, all the subsequent visits are re-evaluated for accuracy.

### Environment
This gear uses the AWS SSM parameter store, and expects that AWS credentials are available in environment variables (`AWS_SECRET_ACCESS_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_DEFAULT_REGION`) within the Flywheel runtime.


### Running
This gear can only be triggered by submission pipeline or finalization pipeline.

### Inputs
- **visits_file**: Input file to trigger the QC process for this participant. [Example](../../gear/form_qc_coordinator/data/example-input.yaml)
- **form_configs_file**: A JSON file with forms module configurations. [Example](../../gear/form_transformer/data/form-data-module-configs.json)
- **qc_configs_file**: JSON file with QC gear config information. [Example](../../gear/form_qc_coordinator/data/qc-gear-configs.json)

### Configs
Gear configs are defined in [manifest.json](../../gear/form_qc_coordinator/src/docker/manifest.json).


## File Metadata and Tagging

This gear manages QC metadata and tags on the visit files it coordinates, not on its own input file. See the [QC Conventions](../nacc_common/qc-conventions.md) reference for details on the data models and conventions used.

1. **File Tag (submission pipeline only)**: When triggered by the submission pipeline, the gear name (e.g., `"form-qc-coordinator"`) is added as a tag to the input visits file, indicating the file has been processed.

2. **Visit File QC Reset**: When re-triggering QC for a visit, the coordinator resets the QC metadata on the visit file using `FileQCModel` and removes existing gear status tags (e.g., `form-qc-checker-PASS` or `form-qc-checker-FAIL`) using the `GearTags` class. This ensures the downstream [Form QC Checker](../form_qc_checker/index.md) starts with a clean state.

   Note: The coordinator does not add QC results to its own input file. QC validation results are managed by the downstream Form QC Checker gear that it triggers for each visit.
