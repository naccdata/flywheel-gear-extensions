file(name="manifest", source="manifest.json")

docker_image(
    name="form-qc-coordinator",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/form_qc_coordinator/src/python/form_qc_coordinator_app:bin",
    ],
    image_tags=["1.4.3", "latest"],
)
