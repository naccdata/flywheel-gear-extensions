file(name="manifest", source="manifest.json")

docker_image(
    name="dicom-qc-checker",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/dicom_qc_checker/src/python/dicom_qc_checker_app:bin",
    ],
    image_tags=["0.0.1", "latest"],
)
