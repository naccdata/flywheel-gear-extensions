# Docs template

A cookiecutter template to create docs for a gear in the monorepo

## Preliminaries 

Within the VS Code devcontainer, run

```bash
pipx install cookiecutter
```

If you are not using the devcontainer, see the [cookiecutter docs](https://cookiecutter.readthedocs.io/en/2.5.0/README.html) for installation.

## Create Docs

Run cookiecutter from the root directory of the monorepo

```bash
cookiecutter templates/docs --output-dir docs/
```

You will then be prompted to instantiate the gear.
Type `enter` to accept the default value, or provide a new value.

```
  [1/3] gear_name (Gear Name): Junk Gear
  [2/3] gear_description (A NACC gear for Flywheel): Description for the Junk Gear
  [3/3] module_name (junk_gear): 
```
