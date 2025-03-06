file(name="manifest", source="manifest.json")

docker_image(name="batch-scheduler",
             source="Dockerfile",
             dependencies=[
                 ":manifest",
                 "gear/batch_scheduler/src/python/batch_scheduler_app:bin"
             ],
             image_tags=["0.0.3", "latest"])
