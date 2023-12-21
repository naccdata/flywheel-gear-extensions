# Common library template

A cookiecutter template to create a new package in the common library of the monorepo.

## Preliminaries

Within the VS Code devcontainer, run

```bash
pipx install cookiecutter
```

If you are not using the devcontainer, see the [cookiecutter docs](https://cookiecutter.readthedocs.io/en/2.5.0/README.html) for installation.

## Create package

Run cookiecutter from the root directory of the monorepo

```bash
cookiecutter templates/common --output-dir common/src/python/
```

You will then be prompted to instantiate the package name.

```
  [1/2] library_name (Library Name): Example Package
  [2/2] package_name (example_package):
```
