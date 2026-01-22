file(name="manifest", source="manifest.json")

docker_image(name="file-aggregator",
             source="Dockerfile",
             dependencies=[":manifest", "gear/file_aggregator/src/python/file_aggregator_app:bin"],
             image_tags=["0.0.1", "latest"])
