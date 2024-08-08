file(name="manifest", source="manifest.json")

docker_image(
    name="redcap-project-creation",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/redcap_project_creation/src/python/redcap_project_creation_app:bin"
    ],
    image_tags=["0.0.1", "latest"])
