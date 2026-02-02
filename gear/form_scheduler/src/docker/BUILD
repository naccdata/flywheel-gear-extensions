file(name="manifest", source="manifest.json")

docker_image(
    name="form-scheduler",
    source="Dockerfile",
    dependencies=[":manifest", "gear/form_scheduler/src/python/form_scheduler_app:bin"],
    image_tags=["1.2.2", "latest"],
)
