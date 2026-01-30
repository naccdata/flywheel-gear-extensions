file(name="manifest", source="manifest.json")

docker_image(name="image-identifier-lookup",
             source="Dockerfile",
             dependencies=[":manifest", "gear/image_identifier_lookup/src/python/image_identifier_lookup_app:bin"],
             image_tags=["0.0.1", "latest"])
