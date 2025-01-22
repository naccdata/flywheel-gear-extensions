FROM python:3.11

ENV BASE_DIR=/flywheel/v0
RUN mkdir -p ${BASE_DIR}/input

WORKDIR ${BASE_DIR}

COPY gear/hello_world/src/docker/manifest.json ${BASE_DIR}
COPY gear.hello_world.src.python.hello_world_app/bin.pex /bin/run

ENTRYPOINT [ "/bin/run" ]