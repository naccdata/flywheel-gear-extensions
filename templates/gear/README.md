# Gear template

A cookiecutter template to create new Gear in the monorepo

## Preliminaries 

Within the VS Code devcontainer, run

```bash
pipx install cookiecutter
```

If you are not using the devcontainer, see the [cookiecutter docs](https://cookiecutter.readthedocs.io/en/2.5.0/README.html) for installation.

## Create Gear

Run cookiecutter from the root directory of the monorepo

```bash
cookiecutter templates/gear --output-dir gear/
```

You will then be prompted to instantiate the gear.
Type `enter` to accept the default value, or provide a new value.

```
  [1/9] gear_name (Gear Name): Junk Gear
  [2/9] gear_description (A NACC gear for Flywheel): A junk gear for trying this out
  [3/9] package_name (junk-gear): 
  [4/9] module_name (junk_gear): 
  [5/9] app_name (junk_gear_app): junk_app
  [6/9] class_name (JunkGear): JunkGearExecution
  [7/9] image_tag (0.0.1):
  [8/9] author (NACC):
  [9/9] maintainer (NACC <nacchelp@uw.edu>):
```
