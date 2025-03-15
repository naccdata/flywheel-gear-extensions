file(name="manifest", source="manifest.json")

docker_image(name="csv-subject-splitter",
             source="Dockerfile",
             dependencies=[
                 ":manifest",
                 "gear/csv_subject_splitter/src/python/csv_app:bin"
             ],
             image_tags=["1.0.4f", "latest"])
