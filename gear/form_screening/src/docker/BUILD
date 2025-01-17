file(name="manifest", source="manifest.json")

docker_image(name="form-screening",
             source="Dockerfile",
             dependencies=[
                 ":manifest",
                 "gear/form_screening/src/python/form_screening_app:bin"
             ],
             image_tags=["0.0.6", "latest"])
