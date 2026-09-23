# faire-hire-anonymizer

## What this is

The standalone PII-anonymization service for FairHire. Wraps
[data-privacy-stack/presidio](https://github.com/data-privacy-stack/presidio)
(vendored as a git submodule at `vendor/presidio`) behind a gateway, deployed
on company-owned hardware on the internal network only.

This repo does not implement anonymization itself — Presidio does. This
repo's own code is entirely the `gateway/` service: a thin Flask app that
proxies an explicit allowlist of routes and merges in a maintained
`allow_list` of tech/framework terms on every `/analyze` call (see
"Conventions" below). There is no application-level auth — access control is
the internal network boundary alone, by decision (see "Deployment / network
exposure").

## Why this exists

FairHire (the main candidate-scoring project — see
`gitlab-ce.convivo.net/prototyping/faire-hire`) strips PII from candidate CVs
before sending them to typesafe.ai for scoring, so the AI never sees a name,
contact detail, or photo. This service is the PII-stripping step in that
pipeline. It has to run somewhere that can be trusted with raw, unredacted CV
text — hence: company hardware, internal network only, not a SaaS/cloud
endpoint.

## Architecture

```
                   internal network only
                  ┌──────────────────────────────────────┐
FairHire pipeline │  gateway (:8080, the only host port)  │
              ──▶│    │ allowlisted routes, no auth        │
                  │    ├──▶ presidio-analyzer (:5001)      │
                  │    │      (ollama: optional, off by default) │
                  │    └──▶ presidio-anonymizer (:5001)    │
                  └──────────────────────────────────────┘
```

- `gateway` is the **only** service with a published host port. `presidio-analyzer`
  and `presidio-anonymizer` have no `ports:` mapping in `docker-compose.yml`
  — they're reachable only on the internal Docker network, from `gateway`.
- `gateway` proxies exactly three routes: `POST /analyze`, `GET
  /supportedentities`, `POST /anonymize`, plus its own `/health`. It does
  **not** proxy `/deanonymize` (which the upstream anonymizer service
  exposes) — FairHire re-identifies candidates through its own PII vault,
  never through Presidio's decrypt operator, so that route is deliberately
  absent here, not just undocumented. The allowlist is enforced by which
  routes exist in the code, not by an auth check.
- `/analyze` merges `gateway/allow_list.json` (a maintained list of
  tech/framework terms — `Kotlin`, `Dart`, `Jetpack Compose`, etc.) into
  every request's `allow_list` field, on top of whatever the caller passes.
  Without this, spaCy's general-purpose NER misreads common tech proper
  nouns as `PERSON` at the same confidence as a real name (confirmed against
  a real CV), which would blank out genuine technical content before scoring
  — this isn't a hypothetical, it's an observed failure mode. Extend
  `allow_list.json` as more false positives turn up in practice.
- **Ollama is optional and off by default.** It's only used by
  `BasicLangExtractRecognizer`, an LLM-based entity extractor that upstream
  ships **disabled** in its default recognizer config — core PII detection
  runs on spaCy (`en_core_web_lg`), and `presidio-analyzer`'s `app.py` never
  contacts Ollama at startup regardless. `docker-compose.yml` puts `ollama`
  behind the `llm-extraction` Compose profile so a plain `docker compose up`
  never starts it (and never conflicts with a native Ollama install already
  using the host's port 11434). Only relevant if someone later reconfigures
  the recognizer registry to turn that extractor on.
- `presidio-image-redactor` (in upstream's own compose file) is not deployed
  at all — FairHire's CVs are text, not images; unused services are just
  attack surface.

## Conventions

- Gateway: Python, Flask, single file (`gateway/app.py`) — deliberately small;
  don't grow this into a general-purpose proxy framework.
- Never log request/response bodies anywhere in the gateway — they may
  contain raw candidate PII. Log method, path, and status only.
- `vendor/presidio` is a git submodule, not vendored source — don't hand-edit
  files inside it. Update it with `git submodule update --remote
  vendor/presidio` and review the diff before committing the bump.

## Deployment / network exposure

This service has **no application-level auth** — by decision, the internal
network boundary alone is the access control. It must therefore never be
reachable from the public internet: `GATEWAY_BIND_HOST` in `.env` must be set
to the internal network interface's IP on production hardware (not left at
the `0.0.0.0` local-dev default), and/or a host firewall rule should restrict
inbound connections on `GATEWAY_PORT` to the internal subnet/VPN range. This
is now the only thing standing between this service and raw, unredacted CV
text being reachable — there's no second layer behind it, so getting the
network boundary right matters more than it would if there were.

## Open items

- The real internal `GATEWAY_BIND_HOST` still needs to be assigned once this
  is actually deployed (tracked as open question 10 in FairHire's
  `IMPLEMENTATION_PLAN.md`). Ollama model/hardware sizing is no longer a
  blocker — see "Architecture" above, it's off by default and not needed for
  the base pipeline.
