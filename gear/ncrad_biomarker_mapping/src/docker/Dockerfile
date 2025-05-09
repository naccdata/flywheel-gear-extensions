FROM python:3.11

ENV BASE_DIR=/flywheel/v0
RUN mkdir -p ${BASE_DIR}/input

WORKDIR ${BASE_DIR}

COPY gear/ncrad_biomarker_mapping/src/docker/manifest.json ${BASE_DIR}
COPY gear.ncrad_biomarker_mapping.src.python.ncrad_biomarker_mapping_app/bin.pex /bin/run

ENTRYPOINT [ "/bin/run" ]