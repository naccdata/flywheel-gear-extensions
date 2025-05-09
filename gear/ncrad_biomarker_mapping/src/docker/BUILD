file(name="manifest", source="manifest.json")

docker_image(
    name="ncrad-biomarker-mapping",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/ncrad_biomarker_mapping/src/python/ncrad_biomarker_mapping_app:bin"
    ],
    image_tags=["0.0.1", "latest"])
