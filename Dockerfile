FROM python:3.12-slim-bookworm

ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd -g ${APP_GID} appgroup || true \
 && useradd -m -u ${APP_UID} -g ${APP_GID} -s /bin/bash appuser || true

WORKDIR /workdir

COPY requirements.txt requirements.txt

RUN pip install -r requirements.txt

COPY app app

RUN chown -R appuser:appgroup app

USER appuser