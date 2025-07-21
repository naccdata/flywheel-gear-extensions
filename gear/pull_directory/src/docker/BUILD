file(name="manifest", source="manifest.json")

docker_image(
    name="pull-directory",
    source="Dockerfile",
    dependencies=[":manifest", "gear/pull_directory/src/python/directory_app:bin"],
    image_tags=["1.0.3", "latest"],
)
