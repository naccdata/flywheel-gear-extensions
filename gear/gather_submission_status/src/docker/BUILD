file(name="manifest", source="manifest.json")

docker_image(
    name="gather-submission-status",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/gather_submission_status/src/python/gather_submission_status_app:bin",
    ],
    image_tags=["1.0.0", "latest"],
)
