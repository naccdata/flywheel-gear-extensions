FROM python:3.11

ENV BASE_DIR=/flywheel/v0
RUN mkdir -p ${BASE_DIR}/input

WORKDIR ${BASE_DIR}

COPY gear/redcap_project_info_management/src/docker/manifest.json ${BASE_DIR}
COPY gear.redcap_project_info_management.src.python.redcap_info_app/bin.pex /bin/run

ENTRYPOINT [ "/bin/run" ]