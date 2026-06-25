file(name="manifest", source="manifest.json")

docker_image(name="center-form-export",
             source="Dockerfile",
             dependencies=[":manifest", "gear/center_form_export/src/python/center_form_export_app:bin"],
             image_tags=["0.0.1", "latest"])
