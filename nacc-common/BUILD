resource(name="pyproject", source="pyproject.toml")
resource(name="readme", source="README.md")
resource(name="license", source="LICENSE")

python_distribution(
    name="dist",
    dependencies=[
        ":pyproject",
        ":readme",
        ":license",
        "nacc-common/src/python:nacc-common-lib",
        "nacc-common/src/python:py_typed",
        "mypy-stubs/src/python/flywheel:lib",
    ],
    wheel=True,
    sdist=True,
    provides=python_artifact(
        name="nacc-common",
        version="1.2.5",
    ),
    # Don't generate setup.py
    generate_setup=False,
)
