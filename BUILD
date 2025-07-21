python_requirement(
    name="lib", requirements=["types-requests"], type_stub_modules=["requests"]
)

python_requirements(
    name="reqs",
    module_mapping={"flywheel-sdk": ["flywheel"]},
    overrides={
        "ssm-parameter-store": {"dependencies": ["//:reqs#setuptools"]},
    },
)

file(name="linux_x86_py311", source="linux_x86_py311.json")

__defaults__(
    {
        pex_binary: dict(complete_platforms=["//:linux_x86_py311"]),
        docker_image: dict(build_platform=["linux/amd64"]),
    }
)
