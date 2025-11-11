file(name="manifest", source="manifest.json")

docker_image(
    name="gather-form-data",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/gather_form_data/src/python/gather_form_data_app:bin",
    ],
    image_tags=["0.1.4", "latest"],
)
