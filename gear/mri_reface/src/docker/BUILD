file(name="manifest", source="manifest.json")

docker_image(
    name="mri-reface",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/mri_reface/src/python/mri_reface_app:bin",
    ],
    image_tags=["0.0.1", "latest"],
)
