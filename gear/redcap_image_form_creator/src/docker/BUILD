file(name="manifest", source="manifest.json")

docker_image(
    name="redcap-image-form-creator",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/redcap_image_form_creator/src/python/redcap_image_form_creator_app:bin",
    ],
    image_tags=["0.0.3", "latest"],
)
