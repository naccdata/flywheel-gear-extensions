file(name="manifest", source="manifest.json")

docker_image(
    name="project-management",
    source="Dockerfile",
    dependencies=[":manifest", "gear/project_management/src/python/project_app:bin"],
    image_tags=["2.1.10", "latest"],
)
