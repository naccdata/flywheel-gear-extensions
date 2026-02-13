file(name="manifest", source="manifest.json")

docker_image(
    name="attribute-curator",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/attribute_curator/src/python/attribute_curator_app:bin",
    ],
    image_tags=["1.3.0", "latest"],
)
