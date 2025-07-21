# REDCap Project Info Management

This gear adds REDCap project information needed to integrate a form project with a center form ingest pipeline in Flywheel.

Reads a YAML file that contains a list of objects such as

```yaml
---
- center-id: sample-program
  study-id: test
  project-label: ingest-form
  projects:
  - redcap-pid: 1
    label: enroll
```

Adds the information to the ingest project metadata for the study within the center group. 


[REDCap to Flywheel Transfer](../redcap_fw_transfer/index.md) gear and the ADRC portal use this information to link between Flywheel ingest projects and REDCap projects.


Gear must be run with admin privileges.
