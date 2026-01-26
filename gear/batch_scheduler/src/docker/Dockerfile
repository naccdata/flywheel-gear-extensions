FROM python:3.12

ENV BASE_DIR=/flywheel/v0
RUN mkdir -p ${BASE_DIR}/input

WORKDIR ${BASE_DIR}

COPY gear/batch_scheduler/src/docker/manifest.json ${BASE_DIR}
COPY gear.batch_scheduler.src.python.batch_scheduler_app/bin.pex /bin/run

ENTRYPOINT [ "/bin/run" ]