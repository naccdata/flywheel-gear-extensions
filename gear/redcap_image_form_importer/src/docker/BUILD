file(name="manifest", source="manifest.json")

docker_image(
    name="redcap-image-form-importer",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/redcap_image_form_importer/src/python/redcap_image_form_importer_app:bin",
    ],
    image_tags=["0.0.6", "latest"],
)
