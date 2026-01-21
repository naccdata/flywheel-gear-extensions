file(name="manifest", source="manifest.json")
file(name="requirements", source="dbt-requirements.txt")

docker_image(
    name="dbt-runner",
    source="Dockerfile",
    dependencies=[
        ":requirements",
        ":manifest",
        "gear/dbt_runner/src/python/dbt_runner_app:bin",
    ],
    image_tags=["0.2.0", "latest"],
)
