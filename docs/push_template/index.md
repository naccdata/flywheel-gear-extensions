# Push Template

Script to push settings from a template project to projects in center groups.

## [Source directory](https://github.com/naccdata/flywheel-gear-extensions/tree/main/push_template)


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

The stage names are hard-coded in the project management script, and are `ingest`, `accepted` and `retrospective`.

Projects that are managed by the script should be in groups with a tag matching the regex `adcid-\d+`.
For example, `adcid-14`.
These tags can be set using the project management script.

## Running from command-line

The script can be run with 

```bash
pants run push_template/src/python/template_app:bin
```

which will push all template projects to pipeline stage projects within tagged groups.

To give command line arguments, add `--` to the command line and give the arguments.
Available arguments are
- `--dry_run` to run the script without making changes, and 
- `--admin_group` to indicate the group in which templates occur. The default admin group is `nacc`.

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
    "new_only": False
}
```

To run the gear use

```python
push_gear.run(config=config, destination=admin_project)
```

This gear doesn't use the destination, but it needs to be set.
Set `admin_project` to a project in the admin group. 
For NACC, use the group `nacc/project-admin`.
