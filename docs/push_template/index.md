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

A template project has a name like `ingest-form-template` where the prefix without `-template` is the prefix of labels of projects in the system.
Concretely, the name should match the regex `^\w+(-[\w]+)*-template$`.

Projects that are managed by the script occur in the groups for centers that are listed in `project.info.centers` of `nacc/metadata`.

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
