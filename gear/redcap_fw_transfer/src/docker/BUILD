file(name="manifest", source="manifest.json")

docker_image(
    name="redcap-fw-transfer",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/redcap_fw_transfer/src/python/redcap_fw_transfer_app:bin",
    ],
    image_tags=["0.1.0", "latest"],
)
