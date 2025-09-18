file(name="manifest", source="manifest.json")

docker_image(
    name="file-distribution",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/file_distribution/src/python/file_distribution_app:bin",
    ],
    image_tags=["0.0.1", "latest"],
)
