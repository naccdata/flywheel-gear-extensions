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
N/A

### Configs
Gear configs are defined in [manifest.json](../../gear/participant_transfer/src/docker/manifest.json).