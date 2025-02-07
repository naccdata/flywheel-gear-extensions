file(name="manifest", source="manifest.json")

docker_image(name="indexing-data-curator",
             source="Dockerfile",
             dependencies=[":manifest", "gear/indexing_data_curator/src/python/indexing_curator_app:bin"],
             image_tags=["0.0.1", "latest"])
