file(name="manifest", source="manifest.json")

docker_image(
    name="ingest-accepted-transfer",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/ingest_accepted_transfer/src/python/ingest_accepted_transfer_app:bin"
    ],
    image_tags=["0.0.2", "latest"])
