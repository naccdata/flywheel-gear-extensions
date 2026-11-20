FROM ghcr.io/astral-sh/uv:0.13.7 AS uv

# Not on a public registry: load mri_reface_0.3.5_docker.zip from NITRC and tag
# it mri_reface:0.3.5 before building (see docs/mri_reface/index.md).
FROM mri_reface:0.3.5

# User the mri_reface image runs as; its home holds the MATLAB Runtime cache.
ARG REFACE_USER=reface-user

USER root

ENV BASE_DIR=/flywheel/v0 \
    UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_PYTHON_BIN_DIR=/usr/local/bin

# The gear pex needs Python 3.12, which the mri_reface image does not provide.
COPY --from=uv /uv /usr/local/bin/uv
RUN uv python install 3.12 \
    && mkdir -p ${BASE_DIR}/input ${BASE_DIR}/output ${BASE_DIR}/work

WORKDIR ${BASE_DIR}

COPY gear/mri_reface/src/docker/manifest.json ${BASE_DIR}
COPY gear.mri_reface.src.python.mri_reface_app/bin.pex /bin/run

RUN chown -R ${REFACE_USER} ${BASE_DIR} \
    && chmod -R a+rwX ${BASE_DIR}

USER ${REFACE_USER}

ENTRYPOINT [ "/bin/run" ]
