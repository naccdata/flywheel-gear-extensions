file(name="manifest", source="manifest.json")

docker_image(
    name="dataset-aggregator",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/dataset_aggregator/src/python/dataset_aggregator_app:bin",
    ],
    image_tags=["0.1.0", "latest"],
)
