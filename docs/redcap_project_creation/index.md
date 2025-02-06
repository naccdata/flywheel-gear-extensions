# REDCap Project Creation

Each project in the form ingest pipeline for a study/center in Flywheel has an associated REDCap project at NACC REDCap instance (for the centers who are going to use direct data entry submission option). This gear uses the REDCap API to automate creation of these REDCap projects.

Gear uses a REDCap super user token to create the necessary projects in REDCap. It updates the AWS parameter store with the API tokens for the newly created projects and adds the mapping information to the respective study/centers metadata projects in Flywheel. 

### Environment
This gear uses the AWS SSM parameter store, and expects that AWS credentials are available in environment variables (`AWS_SECRET_ACCESS_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_DEFAULT_REGION`) within the Flywheel runtime.

### Inputs
YAML file with the details on the REDCap projects to be created for each study/center.

```yaml
---
study-id: test
centers:
  - sample-center
  - example-center
projects:
  - project-label: ingest-form
    modules:
    - label: uds
      title: UDSv4 Direct Entry
    - label: ftld
      title: FTLDv4 Direct Entry
      template: ftld-alt
  - project-label: ingest-enrollment
    modules:
    - label: enroll
      title: Participant Enrollment/Transfer
```

### Running
Gear must be run with admin privileges.

### Configs
Gear configs are defined in [manifest.json](../../gear/redcap_project_creation/src/docker/manifest.json).
