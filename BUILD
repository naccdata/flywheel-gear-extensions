python_requirement(
    name="lib", requirements=["types-requests"], type_stub_modules=["requests"]
)

python_requirements(
    name="reqs",
    module_mapping={"flywheel-sdk": ["flywheel"]},
    overrides={
        "ssm-parameter-store": {"dependencies": ["//:reqs#setuptools"]},
        "flywheel-sdk": {"dependencies": ["//:reqs#pandas"]},
    },
)
