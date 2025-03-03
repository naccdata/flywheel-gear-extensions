file(name="manifest", source="manifest.json")

docker_image(name="uds-curator",
             source="Dockerfile",
             dependencies=[
                 ":manifest", "gear/uds_curator/src/python/uds_curator_app:bin"
             ],
             image_tags=["1.0.0", "latest"])
