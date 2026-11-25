file(name="manifest", source="manifest.json")
docker_image(
    name="loni-receipt-metadata",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/loni_receipt_metadata/src/python/loni_receipt_metadata_app:bin",
    ],
    image_tags=["0.0.1", "latest"],
)
