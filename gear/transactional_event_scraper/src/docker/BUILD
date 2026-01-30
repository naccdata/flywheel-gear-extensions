file(name="manifest", source="manifest.json")

docker_image(
    name="transactional-event-scraper",
    source="Dockerfile",
    dependencies=[
        ":manifest",
        "gear/transactional_event_scraper/src/python/transactional_event_scraper_app:bin",
    ],
    image_tags=["1.0.0", "latest"],
)
