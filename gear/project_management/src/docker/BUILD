file(name="manifest", source="manifest.json")

docker_image(
    name="project-management",
    source="Dockerfile",
    dependencies=[
        ":manifest", "gear/project_management/src/python/project_app:bin"
    ],
    image_tags=["0.0.28", "latest"],
)
