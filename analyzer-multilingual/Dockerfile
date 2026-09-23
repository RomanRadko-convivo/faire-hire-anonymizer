# Extends vendor/presidio/presidio-analyzer with German support, without
# editing anything inside that submodule. The full vendored source is pulled
# in unmodified from the "presidio-source" additional build context (see
# docker-compose.yml); this file only adds two config files on top of it —
# see nlp-config-de-en.yaml and analyzer-conf-de-en.yaml in this directory
# for what and why.
FROM python:3.12-slim@sha256:804ddf3251a60bbf9c92e73b7566c40428d54d0e79d3428194edf40da6521286

ENV PIP_NO_CACHE_DIR=1
ENV UV_PROJECT_ENVIRONMENT=/usr/local

ENV ANALYZER_CONF_FILE=presidio_analyzer/conf/analyzer-conf-de-en.yaml
ENV RECOGNIZER_REGISTRY_CONF_FILE=presidio_analyzer/conf/default_recognizers.yaml
ENV NLP_CONF_FILE=presidio_analyzer/conf/nlp-config-de-en.yaml

ENV PORT=3000
ENV WORKERS=1

WORKDIR /app

RUN apt-get update \
  && apt-get install curl --no-install-recommends -y \
  && rm -rf /var/lib/apt/lists/*

# Full vendored Presidio analyzer source, unmodified.
COPY --from=presidio-source . /app/

# Our own multilingual configs, layered on top of the vendored ones.
COPY nlp-config-de-en.yaml /app/${NLP_CONF_FILE}
COPY analyzer-conf-de-en.yaml /app/${ANALYZER_CONF_FILE}

RUN pip install uv==0.11.6 \
    && uv sync --locked --no-cache --no-default-groups --extra server --no-install-project

# Presidio requires the analyzer engine's, the NLP engine's, and the
# recognizer registry's supported_languages to match exactly, or it refuses
# to boot ("Misconfigured engine, supported languages have to be
# consistent"). The registry file is vendored (700+ line
# default_recognizers.yaml) — patch its one relevant field on the in-image
# copy rather than hand-maintain a full duplicate that could drift from
# upstream. This never touches the vendored submodule on disk, only the
# copy already inside this build stage.
RUN python -c "\
import yaml; \
path = '${RECOGNIZER_REGISTRY_CONF_FILE}'; \
data = yaml.safe_load(open(path)); \
data['supported_languages'] = sorted(set(data.get('supported_languages', [])) | {'de'}); \
yaml.safe_dump(data, open(path, 'w'), allow_unicode=True, sort_keys=False)"

RUN python install_nlp_models.py \
    --conf_file ${NLP_CONF_FILE} \
    --analyzer_conf_file ${ANALYZER_CONF_FILE}

RUN useradd -m -u 1001 presidio && chown -R presidio:presidio /app

USER 1001

EXPOSE ${PORT}
HEALTHCHECK --interval=30s --timeout=3s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1
CMD ["./entrypoint.sh"]
