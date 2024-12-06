file(name="manifest", source="manifest.json")

docker_image(name="push-template",
             source="Dockerfile",
             dependencies=[
                 ":manifest", "gear/push_template/src/python/template_app:bin"
             ],
             image_tags=["1.0.3", "latest"])
