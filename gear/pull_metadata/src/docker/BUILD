file(name="manifest", source="manifest.json")

docker_image(
    name="pull-metadata",
    source="Dockerfile",
    dependencies=[
        ":manifest", "gear/pull_metadata/src/python/metadata_app:bin"
    ],
    image_tags=["0.0.11", "latest"],
)
