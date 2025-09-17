file(name="manifest", source="manifest.json")

docker_image(
    name="redcap-project-info-management",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/redcap_project_info_management/src/python/redcap_info_app:bin",
    ],
    image_tags=["1.0.0", "latest"],
)
