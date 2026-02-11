file(name="openapi_schema", source="coreapi.yaml")

run_shell_command(
    name="build_client",
    command="docker run --rm -v $PWD:/local openapitools/openapi-generator-cli:v7.2.0 generate " \
        "-i /local/coreapi.yaml -g python -o /local/coreapi/src/python " \
        "--package-name coreapi_client " \
        "--additional-properties='generateSourceCodeOnly=True'",
    execution_dependencies=[":openapi_schema"]
)

experimental_wrap_as_python_sources(name="coreapi_client",
                                    inputs=[":build_client"])
