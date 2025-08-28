python_distribution(
    name="dist",
    dependencies=[
        "nacc-common/src/python:nacc-common-lib",
        "nacc-common/src/python:py_typed",
        "mypy-stubs/src/python/flywheel:lib"
    ],
    wheel=True,
    sdist=True,
    provides=python_artifact(
        name="nacc-common",
        version="1.2.5",
        description="NACC Data Platform utilities",
        author="NACC",
        author_email="nacchelp@uw.edu",
        url="https://github.com/naccdata/flywheel-gear-extensions/nacc-common",
    ),
)
