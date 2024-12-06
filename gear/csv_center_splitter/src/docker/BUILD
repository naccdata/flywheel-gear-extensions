file(name="manifest", source="manifest.json")

docker_image(
    name="csv-center-splitter",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/csv_center_splitter/src/python/csv_center_splitter_app:bin"
    ],
    image_tags=["0.1.0", "latest"])
