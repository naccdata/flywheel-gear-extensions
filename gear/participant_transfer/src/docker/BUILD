file(name="manifest", source="manifest.json")

docker_image(
    name="participant-transfer",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/participant_transfer/src/python/participant_transfer_app:bin",
    ],
    image_tags=["0.0.9", "latest"],
)
