# Common library template

A cookiecutter template to create a new package in the common library of the monorepo.

## Preliminaries

Within the VS Code devcontainer, run

```bash
pipx install cookiecutter
```

If you are not using the devcontainer, see the [cookiecutter docs](https://cookiecutter.readthedocs.io/en/2.5.0/README.html) for installation.

## Create package

Run cookiecutter from the root directory of the monorepo:

```bash
cookiecutter templates/common --output-dir common
```

You will be prompted to instantiate the package name:

```
  [1/2] library_name (Library Name): Example Package
  [2/2] package_name (example_package):
  [3/3] test_name (example_package_test):
```

This will create:
```
common/
├── src/python/example_package/
│   ├── BUILD
│   ├── __init__.py
│   └── example_package.py
└── test/python/example_package_test/
    ├── BUILD
    └── .gitkeep
```

**Note:** You can specify a different output directory if needed for custom package hierarchies.
