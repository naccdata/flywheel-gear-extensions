file(name="manifest", source="manifest.json")

docker_image(name="loni_csv_metadata_processor",
             source="Dockerfile",
             dependencies=[":manifest", "gear/loni_csv_metadata_processor/src/python/loni_csv_metadata_processor_app:bin"],
             image_tags=["0.0.1", "latest"])
