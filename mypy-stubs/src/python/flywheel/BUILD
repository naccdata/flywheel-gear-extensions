python_sources(name="lib", skip_ruff=True)

python_distribution(
    name="dist",
    dependencies=[":lib"],
    wheel=True,
    sdist=True,
    provides=python_artifact(
        name="nacc-flywheel-types",
        version="0.0.1",
        description="NACC flywheel type stubs",
        author="NACC",
        author_email="nacchelp@uw.edu",
        url="https://github.com/naccdata/flywheel-gear-extensions"
    )
)