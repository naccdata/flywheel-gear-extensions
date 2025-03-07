# Batch Scheduler

Schedule batch runs of another utility/analysis gear on the list of centers retrieved from NACC group metadata project.

### Logic
1. Pulls the current list of centers from nacc/metadata project custom information
2. Adds the qualified centers to a batch pool
   - Exclude any centers or studies specified in gear configs `exclude_centers` or `exclude_studies` lists
   - If a valid `time_interval` specified in gear configs, skip the centers which have a successful run of the specified gear within that time interval
3. Trigger the specified utility/analysis gear on batches of centers
   - Number of centers to include in a batch is determined by `batch_mode` and `batch_size` configs in specified in `batch_configs_file`
4. Repeat 3 until the batch pool is empty


### Environment
This gear uses the AWS SSM parameter store, and expects that AWS credentials are available in environment variables (`AWS_SECRET_ACCESS_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_DEFAULT_REGION`) within the Flywheel runtime.


### Running
This gear can only be run in NACC admin group. Set `dry_run` = `True` to just print the list of qualified centers.

### Inputs
**batch_configs_file**: A JSON file with batch run configurations. 
```json
{
    "source": "retrospective-form",
    "target": "accepted",
    "substitute": true,
    "batch_mode": "files",
    "batch_size": 10000,
    "gear_name": "test-gear",
    "gear_configs": {
        "debug": false,
        "source_id": "{{source}}",
        "target_id": "{{target}}",
        "tag": "test-passed"
    }
}
```
- source: Flywheel source project label to trigger the utility/analysis gear
- target (optional): Flywheel target project label, if required by the gear to be triggered
- substitute: Whether to substitute source project and target project ids in utility/analysis gear configs. Default is `false`
- batch_mode: ['projects', 'files'], if set to `projects` count the projects, else count the acquisition files to compute the batch size
- batch_size: Max number of projects/files to include for a batch
- gear_name: Name of the utility/analysis gear to be triggered
- gear_configs: Configs for the utility/analysis gear to be triggered

 
### Configs
Batch Scheduler gear configs are defined in [manifest.json](../../gear/batch_scheduler/src/docker/manifest.json).
