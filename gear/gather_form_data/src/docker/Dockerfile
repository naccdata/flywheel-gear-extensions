FROM python:3.12

ENV BASE_DIR=/flywheel/v0
RUN mkdir -p ${BASE_DIR}/input

WORKDIR ${BASE_DIR}

COPY gear/gather_form_data/src/docker/manifest.json ${BASE_DIR}
COPY gear.gather_form_data.src.python.gather_form_data_app/bin.pex /bin/run

ENTRYPOINT [ "/bin/run" ]