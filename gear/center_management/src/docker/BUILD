file(name="manifest", source="manifest.json")

docker_image(
    name="center-management",
    source="Dockerfile",
    dependencies=[
        ":manifest", "gear/center_management/src/python/center_app:bin"
    ],
    image_tags=["1.0.4", "latest"],
)
