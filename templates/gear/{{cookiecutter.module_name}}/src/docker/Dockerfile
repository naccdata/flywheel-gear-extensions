FROM python:3.12

ENV BASE_DIR=/flywheel/v0
RUN mkdir -p ${BASE_DIR}/input

WORKDIR ${BASE_DIR}

COPY gear/{{cookiecutter.module_name}}/src/docker/manifest.json ${BASE_DIR}
COPY gear.{{cookiecutter.module_name}}.src.python.{{cookiecutter.app_name}}/bin.pex /bin/run

ENTRYPOINT [ "/bin/run" ]