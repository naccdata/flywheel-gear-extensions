# Push Template

Script to push settings from a template project to projects in center groups.

## [Source directory](https://github.com/naccdata/flywheel-gear-extensions/tree/main/gear/push_template)


## Flywheel configuration

The script expects that there is a group containing template projects.
The following are copied from a template project:

- gear rules and any associated files
- user permissions
- the project description (may use `$adrc` as the placeholder for the center name)
- applications

A template project has a name like `form-ingest-template` where the first word is the datatype and the second is a pipeline stage.
Concretely, the name should match the regex `^((\w+)-)?(\w+)-template$`.
Note that the first group is optional, so possible names are `form-ingest-template` or `accepted-template`.
The datatype names must match those used in the project description file used in the [project management script](../project_management/index.md).

The stage names are hard-coded in the project management script, and are `ingest`, `accepted` and `retrospective` for aggregation projects and `distribution` for distribution projects.

Projects that are managed by the script should be in groups with a tag matching the regex `adcid-\d+`.
For example, `adcid-14`.
These tags can be set using the project management script.

## Running from a batch script

Flywheel utility gears are either triggered by a gear rule, or run from a batch script.

```python
import flywheel

client = flywheel.Client(os.environment.get("FW_API_KEY"))
push_gear = client.lookup("gears/push-template")
```

The equivalent of the command line arguments above are given in the `config` argument shown here with default values

```python
config = {
    "dry_run": False,
    "admin_group": "nacc",
    "new_only": False,
    "template_project": "form-ingest-template",
    "template_group": "nacc"
}
```

To run the gear use

```python
push_gear.run(config=config, destination=admin_project)
```

This gear doesn't use the destination, but it needs to be set.
Set `admin_project` to a project in the admin group. 
For NACC, use the group `nacc/project-admin`.
