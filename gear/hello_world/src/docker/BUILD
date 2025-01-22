file(name="manifest", source="manifest.json")

docker_image(name="hello-world",
             source="Dockerfile",
             dependencies=[":manifest", "gear/hello_world/src/python/hello_world_app:bin"],
             image_tags=["0.0.1c", "latest"])
