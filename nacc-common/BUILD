resource(name="pyproject", source="pyproject.toml")
resource(name="readme", source="README.md")
resource(name="license", source="LICENSE")

python_distribution(
    name="dist",
    dependencies=[
        ":pyproject",
        ":readme",
        ":license",
        "nacc-common/src/python/nacc_common:nacc-common-lib",
        "nacc-common/src/python/nacc_common:py_typed",
    ],
    wheel=True,
    sdist=True,
    provides=python_artifact(
        name="nacc-common",
        version="3.1.0",
    ),
    # Don't generate setup.py
    generate_setup=False,
)
