file(name="manifest", source="manifest.json")

docker_image(name="form-deletion",
             source="Dockerfile",
             dependencies=[":manifest", "gear/form_deletion/src/python/form_deletion_app:bin"],
             image_tags=["0.0.1", "latest"])
