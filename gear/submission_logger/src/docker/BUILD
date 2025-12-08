file(name="manifest", source="manifest.json")

docker_image(
    name="submission-logger",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/submission_logger/src/python/submission_logger_app:bin",
    ],
    image_tags=["0.0.1", "latest"],
)
