FROM python:3.12

ENV BASE_DIR=/flywheel/v0
RUN mkdir -p ${BASE_DIR}/input

WORKDIR ${BASE_DIR}

COPY gear/push_template/src/docker/manifest.json ${BASE_DIR}
COPY gear.push_template.src.python.template_app/bin.pex /bin/run

ENTRYPOINT [ "/bin/run" ]