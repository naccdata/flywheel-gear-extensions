file(name="manifest", source="manifest.json")

docker_image(
    name="form-qc-checker",
    source="Dockerfile",
    dependencies=[":manifest", "gear/form_qc_checker/src/python/form_qc_app:bin"],
    image_tags=["1.7.4", "latest"],
)
