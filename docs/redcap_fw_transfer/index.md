# REDCap to Flywheel Transfer

Each project in the form ingest pipeline for a study/center in Flywheel has an associated REDCap project at NACC REDCap instance (for the centers who are going to use direct data entry submission option). This gear uses the REDCap API to pull the completed visit records from a REDCap project and upload it to the respective form ingest project in Flywheel as a CSV file.

This gear uses REDCap project information stored in the center group's metadata proejct to link between REDCap and Flywheel projects.


### Environment
This gear uses the AWS SSM parameter store, and expects that AWS credentials are available in environment variables (`AWS_SECRET_ACCESS_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_DEFAULT_REGION`) within the Flywheel runtime.

### Inputs
JSON schema file defining the accepted fields for each module to be transferred to this project. These files should be named as **[module]-schema.json** (e.g. uds-schema.json, enroll-schema.json) and should be available in the Flywheel ingest project's project files section. 

### Running
This gear is triggered nightly (via a AWS Lambda function) for each form ingest project in a study/center.

### Configs
Gear configs are defined in [manifest.json](../../gear/redcap_fw_transfer/src/docker/manifest.json).
