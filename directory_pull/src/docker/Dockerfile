FROM python:3.10

ENV BASE_DIR=/flywheel/v0
RUN mkdir -p ${BASE_DIR}/input

WORKDIR ${BASE_DIR}

COPY directory_pull/src/docker/manifest.json ${BASE_DIR}
COPY directory_pull.src.python.directory_app/bin.pex /bin/run

ENTRYPOINT [ "/bin/run" ]