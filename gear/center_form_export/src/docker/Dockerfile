FROM python:3.12

ENV BASE_DIR=/flywheel/v0
RUN mkdir -p ${BASE_DIR}/input

WORKDIR ${BASE_DIR}

COPY gear/center_form_export/src/docker/manifest.json ${BASE_DIR}
COPY gear.center_form_export.src.python.center_form_export_app/bin.pex /bin/run

ENTRYPOINT [ "/bin/run" ]