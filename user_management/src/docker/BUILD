file(name="manifest", source="manifest.json")

docker_image(
    name="user-management",
    source="Dockerfile",
    dependencies=[":manifest", "user_management/src/python/user_app:bin"],
    image_tags=["0.0.1", "latest"])
