file(name="manifest", source="manifest.json")

docker_image(
    name="redcap-error-checks-import",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/redcap_error_checks_import/src/python/redcap_error_checks_import_app:bin"
    ],
    image_tags=["0.1.0", "latest"])
