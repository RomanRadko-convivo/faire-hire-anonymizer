# faire-hire-anonymizer

Standalone PII-anonymization service for [FairHire](https://gitlab-ce.convivo.net/prototyping/faire-hire).
Wraps [data-privacy-stack/presidio](https://github.com/data-privacy-stack/presidio)
behind a gateway, meant to run on company-owned hardware on the internal
network only. No application-level auth — the internal network boundary is
the access control, by decision.

See `CLAUDE.md` for the architecture and the reasoning behind it.

## Setup

```sh
git clone --recurse-submodules git@github.com:RomanRadko-convivo/faire-hire-anonymizer.git
cd faire-hire-anonymizer

# if you cloned without --recurse-submodules:
git submodule update --init --recursive

cp .env.example .env
```

Edit `.env`:
- `GATEWAY_BIND_HOST` — **on production hardware, set this to the internal
  network interface's IP**, not the `0.0.0.0` local-dev default. This is the
  only access control this service has — see "Deployment / network exposure"
  in `CLAUDE.md`.

```sh
docker compose up --build
```

This builds and starts `presidio-analyzer`, `presidio-anonymizer`, and
`gateway`. (The `ollama` service is optional and off by default — it's only
needed for an LLM-based extractor upstream ships disabled; see `CLAUDE.md`.
It won't start or get pulled unless you run `docker compose --profile
llm-extraction up`.)

## Usage

```sh
# liveness check
curl http://localhost:8080/health

# detect PII entities in text
curl -X POST http://localhost:8080/analyze \
  -H "Content-Type: application/json" \
  -d '{"text": "Jane Doe, jane.doe@example.com, +1 555-0100", "language": "en"}'

# anonymize text given analyzer results
curl -X POST http://localhost:8080/anonymize \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Jane Doe, jane.doe@example.com, +1 555-0100",
    "analyzer_results": []
  }'
```

`/analyze` automatically merges `gateway/allow_list.json` (a maintained list
of tech/framework terms) into the request, so words like `Kotlin` or `Dart`
don't get misdetected as `PERSON` and redacted out of a CV before scoring —
confirmed against a real CV during testing, not a hypothetical. You can pass
your own `allow_list` in the request too; it's merged in on top, not
replaced.

In the FairHire pipeline, point `PRESIDIO_SERVICE_URL` at this gateway's
internal address (e.g. `http://<internal-host>:8080`).

## What's deliberately not here

- **`/deanonymize`** — the upstream anonymizer service supports decrypting a
  reversible anonymization, but this gateway doesn't proxy it. FairHire
  re-identifies candidates through its own PII vault (keyed by candidate id),
  never through Presidio's decrypt operator, so that capability isn't
  reachable through this service at all.
- **`presidio-image-redactor`** — upstream's own `docker-compose.yml`
  includes it; this one doesn't deploy it. FairHire's CVs are text, and an
  unused service is just attack surface.
- **Authentication** — by decision, this service relies on network-level
  access control only (internal network, never public). See "Deployment /
  network exposure" in `CLAUDE.md`.
- **A public endpoint** — this service is meant to be reachable only from
  the internal company network the FairHire pipeline also runs on. Don't put
  it behind a public load balancer or expose `GATEWAY_PORT` to the internet.

## Status

Built and verified locally: analyze→anonymize flow tested end-to-end
(synthetic text and a real CV), auth removed per decision, `allow_list`
mechanism added and confirmed to suppress tech-term false positives. Not yet
deployed on real company hardware — the real internal `GATEWAY_BIND_HOST`
still needs to be assigned once it is (tracked as open question 10 in
FairHire's `IMPLEMENTATION_PLAN.md`).
