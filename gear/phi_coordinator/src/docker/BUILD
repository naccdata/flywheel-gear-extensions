file(name="manifest", source="manifest.json")

docker_image(
    name="phi-coordinator",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/phi_coordinator/src/python/phi_coordinator_app:bin",
    ],
    image_tags=["0.0.1", "latest"],
)
