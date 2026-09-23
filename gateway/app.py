"""Gateway in front of Presidio's analyzer/anonymizer services.

No authentication — this service is only ever reachable on the internal
company network (never a public endpoint), and that network boundary is
considered sufficient access control here.

Routes are an explicit allowlist, not a generic proxy. In particular,
/deanonymize (which the anonymizer service does expose) is intentionally NOT
proxied: FairHire's architecture re-identifies candidates through its own PII
vault, never through Presidio's decrypt operator, so this gateway refuses to
carry that request at all.

/analyze also merges a maintained allow_list of known tech/framework terms
(gateway/allow_list.json) into every request, so words like "Kotlin" or
"Dart" aren't misdetected as PERSON entities and redacted out of a CV before
scoring — see that file for how to extend it. Caller-supplied allow_list
entries (if any) are merged in on top, never replaced.

Never logs request/response bodies — they may contain raw candidate PII.
"""

import json
import logging
import os
from pathlib import Path

import requests
from flask import Flask, Response, jsonify, request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("anonymizer-gateway")

ANALYZER_URL = os.environ.get("ANALYZER_URL", "http://presidio-analyzer:5001")
ANONYMIZER_URL = os.environ.get("ANONYMIZER_URL", "http://presidio-anonymizer:5001")
UPSTREAM_TIMEOUT = float(os.environ.get("UPSTREAM_TIMEOUT_SECONDS", "30"))

ALLOW_LIST_PATH = Path(__file__).parent / "allow_list.json"
DEFAULT_ALLOW_LIST = json.loads(ALLOW_LIST_PATH.read_text())

app = Flask(__name__)


def _proxy(method: str, upstream_base: str, upstream_path: str, body=None) -> Response:
    url = f"{upstream_base}{upstream_path}"
    if body is None:
        body = request.get_json(silent=True)
    try:
        upstream = requests.request(
            method,
            url,
            params=request.args,
            json=body,
            timeout=UPSTREAM_TIMEOUT,
        )
    except requests.RequestException:
        logger.exception("upstream request failed: %s %s", method, upstream_path)
        return jsonify(error="upstream unavailable"), 502

    logger.info("proxied %s %s -> %s", method, upstream_path, upstream.status_code)
    return Response(upstream.content, status=upstream.status_code, content_type=upstream.headers.get("Content-Type"))


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.post("/analyze")
def analyze():
    body = request.get_json(silent=True) or {}
    caller_allow_list = body.get("allow_list") or []
    body["allow_list"] = sorted(set(DEFAULT_ALLOW_LIST) | set(caller_allow_list))
    return _proxy("POST", ANALYZER_URL, "/analyze", body=body)


@app.get("/supportedentities")
def supported_entities():
    return _proxy("GET", ANALYZER_URL, "/supportedentities")


@app.post("/anonymize")
def anonymize():
    return _proxy("POST", ANONYMIZER_URL, "/anonymize")


# Intentionally no /deanonymize, /recognizers, or catch-all route — anything
# not listed above 404s by default. See module docstring.
