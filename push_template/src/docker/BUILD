file(name="manifest", source="manifest.json")

docker_image(
    name="push-template",
    source="Dockerfile",
    dependencies=[":manifest", "push_template/src/python/template_app:bin"],
    image_tags=["0.0.6", "latest"])
