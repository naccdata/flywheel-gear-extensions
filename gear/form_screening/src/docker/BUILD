file(name="manifest", source="manifest.json")

docker_image(
    name="form-screening",
    source="Dockerfile",
    dependencies=[":manifest", "gear/form_screening/src/python/form_screening_app:bin"],
    image_tags=["1.2.2", "latest"],
)
