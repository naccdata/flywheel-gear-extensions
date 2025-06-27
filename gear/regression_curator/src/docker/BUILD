file(name="manifest", source="manifest.json")

docker_image(
    name="regression-curator",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/regression_curator/src/python/regression_curator_app:bin",
    ],
    image_tags=["0.1.2", "latest"],
)
