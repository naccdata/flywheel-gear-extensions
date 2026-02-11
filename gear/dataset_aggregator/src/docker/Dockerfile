FROM python:3.12

ENV BASE_DIR=/flywheel/v0
RUN mkdir -p ${BASE_DIR}/input

WORKDIR ${BASE_DIR}

COPY gear/dataset_aggregator/src/docker/manifest.json ${BASE_DIR}
COPY gear.dataset_aggregator.src.python.dataset_aggregator_app/bin.pex /bin/run

ENTRYPOINT [ "/bin/run" ]