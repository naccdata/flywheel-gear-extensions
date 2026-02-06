FROM python:3.11

ENV BASE_DIR=/flywheel/v0
RUN mkdir -p ${BASE_DIR}/input

WORKDIR ${BASE_DIR}

COPY gear/transactional_event_scraper/src/docker/manifest.json ${BASE_DIR}
COPY gear.transactional_event_scraper.src.python.transactional_event_scraper_app/bin.pex /bin/run

ENTRYPOINT [ "/bin/run" ]