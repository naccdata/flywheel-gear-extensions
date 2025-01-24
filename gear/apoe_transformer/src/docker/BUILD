file(name="manifest", source="manifest.json")

docker_image(name="apoe-transformer",
             source="Dockerfile",
             dependencies=[
                 ":manifest",
                 "gear/apoe_transformer/src/python/apoe_transformer_app:bin"
             ],
             image_tags=["0.1.3", "latest"])
