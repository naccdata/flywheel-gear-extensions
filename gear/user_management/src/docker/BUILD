file(name="manifest", source="manifest.json")

docker_image(
    name="user-management",
    source="Dockerfile",
    dependencies=[":manifest", "gear/user_management/src/python/user_app:bin"],
    image_tags=["3.4.1", "latest"],
)
