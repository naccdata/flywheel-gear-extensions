file(name="manifest", source="manifest.json")

docker_image(
    name="legacy-sanity-check",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/legacy_sanity_check/src/python/legacy_sanity_check_app:bin",
    ],
    image_tags=["1.0.0", "latest"],
)
