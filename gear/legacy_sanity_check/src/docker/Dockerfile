FROM python:3.11

ENV BASE_DIR=/flywheel/v0
RUN mkdir -p ${BASE_DIR}/input

WORKDIR ${BASE_DIR}

COPY gear/legacy_sanity_check/src/docker/manifest.json ${BASE_DIR}
COPY gear.legacy_sanity_check.src.python.legacy_sanity_check_app/bin.pex /bin/run

ENTRYPOINT [ "/bin/run" ]