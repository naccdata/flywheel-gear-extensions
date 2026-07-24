file(name="manifest", source="manifest.json")

docker_image(
    name="pipeline-event-logger",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/pipeline_event_logger/src/python/pipeline_event_logger_app:bin",
    ],
    image_tags=["0.2.0", "latest"],
)
