file(name="manifest", source="manifest.json")

docker_image(
    name="identifier-provisioning",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/identifier_provisioning/src/python/identifier_provisioning_app:bin",
    ],
    image_tags=["2.0.1", "latest"],
)
