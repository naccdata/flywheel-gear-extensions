FROM python:3.11

ENV BASE_DIR=/flywheel/v0
RUN mkdir -p ${BASE_DIR}/input

WORKDIR ${BASE_DIR}

COPY gear/loni_csv_metadata_processor/src/docker/manifest.json ${BASE_DIR}
COPY gear.loni_csv_metadata_processor.src.python.loni_csv_metadata_processor_app/bin.pex /bin/run

ENTRYPOINT [ "/bin/run" ]