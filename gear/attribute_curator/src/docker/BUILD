file(name="manifest", source="manifest.json")

docker_image(
    name="attribute-curator",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/attribute_curator/src/python/attribute_curator_app:bin",
    ],
    image_tags=["0.4.1", "latest"],
)
