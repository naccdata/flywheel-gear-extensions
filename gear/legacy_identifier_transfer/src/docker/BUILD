file(name="manifest", source="manifest.json")

docker_image(
    name="legacy-identifier-transfer",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/legacy_identifier_transfer/src/python/legacy_identifier_transfer_app:bin"
    ],
    image_tags=["0.0.3", "latest"])
