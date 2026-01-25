FROM mcr.microsoft.com/devcontainers/python:2-3.11-bullseye

USER root
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && rm -f /usr/share/keyrings/yarn.gpg \
    && apt-get update
