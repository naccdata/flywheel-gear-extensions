file(name="manifest", source="manifest.json")

docker_image(name="form-transformer",
             source="Dockerfile",
             dependencies=[
                 ":manifest",
                 "gear/form_transformer/src/python/form_csv_app:bin"
             ],
             image_tags=["1.0.11", "latest"])
