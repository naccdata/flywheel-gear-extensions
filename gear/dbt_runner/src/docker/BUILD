file(name="manifest", source="manifest.json")

docker_image(name="dbt-runner",
             source="Dockerfile",
             dependencies=[":manifest", "gear/dbt_runner/src/python/dbt_runner_app:bin"],
             image_tags=["0.0.1", "latest"])
