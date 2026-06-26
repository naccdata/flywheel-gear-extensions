# Form Deletion Gear

This gear processes the delete requests for existing form data submissions.

### Environment
This gear uses the AWS SSM parameter store, and expects that AWS credentials are available in environment variables (`AWS_SECRET_ACCESS_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_DEFAULT_REGION`) within the Flywheel runtime.

### Inputs
- **request_file**: A JSON file with delete request information.
  
```json
{ 
  "module": "UDS",
  "ptid": "test1234",
  "visitdate": "2025-01-02",
  "timestamp": "2026-04-13T05:41:25.705Z",
  "requested_by": "testuser@uw.edu"
}

```
- **form_configs_file**: A JSON file with forms module configurations. [Example](../../gear/form_transformer/data/form-data-module-configs.json)

### Configs
Gear configs are defined in [manifest.json](../../gear/form_deletion/src/docker/manifest.json).