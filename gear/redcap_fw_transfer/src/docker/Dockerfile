FROM python:3.12

ENV BASE_DIR=/flywheel/v0
RUN mkdir -p ${BASE_DIR}/input

WORKDIR ${BASE_DIR}

COPY gear/redcap_fw_transfer/src/docker/manifest.json ${BASE_DIR}
COPY gear.redcap_fw_transfer.src.python.redcap_fw_transfer_app/bin.pex /bin/run

ENTRYPOINT [ "/bin/run" ]