file(name="manifest", source="manifest.json")

docker_image(
    name="phi-image-removal",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/phi_image_removal/src/python/phi_image_removal_app:bin",
    ],
    image_tags=["0.0.1", "latest"],
)
