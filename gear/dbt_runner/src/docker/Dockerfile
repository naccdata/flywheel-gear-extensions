FROM python:3.12

ENV BASE_DIR=/flywheel/v0
RUN mkdir -p ${BASE_DIR}/input

WORKDIR ${BASE_DIR}

COPY gear/dbt_runner/src/docker/dbt-requirements.txt ${BASE_DIR}
RUN pip install --no-cache-dir -r ${BASE_DIR}/dbt-requirements.txt

COPY gear/dbt_runner/src/docker/manifest.json ${BASE_DIR}
COPY gear.dbt_runner.src.python.dbt_runner_app/bin.pex /bin/run

ENTRYPOINT [ "/bin/run" ]