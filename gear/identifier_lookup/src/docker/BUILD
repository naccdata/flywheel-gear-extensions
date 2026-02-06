file(name="manifest", source="manifest.json")

docker_image(
    name="identifier-lookup",
    source="Dockerfile",
    dependencies=[":manifest", "gear/identifier_lookup/src/python/identifier_app:bin"],
    image_tags=["2.2.2", "latest"],
)
