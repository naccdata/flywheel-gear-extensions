file(name="manifest", source="manifest.json")

docker_image(
    name="identifier-provisioning",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/identifier_provisioning/src/python/identifier_provisioning_app:bin",
    ],
    image_tags=["1.0.8", "latest"],
)
