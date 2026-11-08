# Participant Transfer
This gear processes a participant transfer between two centers. 
- Updates the identifiers database
- Updates subject/session level info in enrollment projects for previous center and receiving center
- Soft links participant data from previous center to receiving center in NACC Data Platform

### Environment
This gear uses the AWS SSM parameter store, and expects that AWS credentials are available in environment variables (`AWS_SECRET_ACCESS_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_DEFAULT_REGION`) within the Flywheel runtime.

### Running
This is a NACC Admin gear, should only be triggered in NACC group by an Admin.

### Inputs
* `soft_copy_configs`: JSON file with the configuration for the gear that copies participant data between centers. Must be uploaded as a project file. See [participant-transfer-soft-copy-configs.json](../../gear/participant_transfer/src/data/participant-transfer-soft-copy-configs.json) for an example.

The `include-filter` and `target-project` configs depend on the participant and the destination project, so they must contain the `{{subject}}` and `{{target}}` placeholders respectively. These are substituted at runtime with the NACCID being transferred and the Flywheel ID of each destination project.

### Configs
Gear configs are defined in [manifest.json](../../gear/participant_transfer/src/docker/manifest.json).