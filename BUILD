python_requirement(
    name="lib", requirements=["types-requests"], type_stub_modules=["requests"]
)

python_requirements(
    name="reqs",
    module_mapping={"flywheel-sdk": ["flywheel"]},
)

python_requirement(
    name="mypy", requirements=["mypy>=1.11.1", "pydantic>=2.5.2"], resolve="mypy"
)

file(name="linux_x86_py312", source="linux_x86_py312.json")

__defaults__(
    {
        pex_binary: dict(complete_platforms=["//:linux_x86_py312"]),
        docker_image: dict(build_platform=["linux/amd64"]),
    }
)

shell_sources(
    name="root",
)
