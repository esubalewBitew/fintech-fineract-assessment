# fineract-assessment

Take-home: Apache Fineract GL `externalReference` (patches) + **Integration middleware** + **Mock ERP** ledger (Python).

Pinned Fineract tag: `1.16.1`

## Layout

| Path | Brief |
|------|--------|
| `fineract-customization/patches/` | CBS customization (A) |
| `ARCHITECTURE.md` / `DECISIONS.md` / `API.md` | Design + API notes |
| `mock-erp/` | G — ledger with journals |
| `integration-service/` | A-sync, E–K middleware |
| `scripts/fineract_setup_part_b.py` | Part B — office / RWF / product / API user |
| `postman/` | `collection.json` + `environment.json` |
| `evidence/` | Step scenario logs + JSON outputs |
| `docker-compose.yml` | Postgres + Fineract + Mock ERP + Integration |

## Run

```bash
cd fineract-assessment
docker compose build
docker compose up -d
# Fineract https://localhost:8443
# Mock ERP  http://localhost:8081
# Integration http://localhost:8082
```

Apps connect as dedicated owners (`mock_erp` / `integration`), not `root` — see `02-assessment-dbs.sh`.

If the Postgres volume already existed before those roles/DBs:

```bash
docker compose exec db psql -U root -c "CREATE USER mock_erp WITH PASSWORD 'mock_erp_secret';"
docker compose exec db psql -U root -c "CREATE USER integration WITH PASSWORD 'integration_secret';"
docker compose exec db psql -U root -c "CREATE DATABASE mock_erp OWNER mock_erp;"
docker compose exec db psql -U root -c "CREATE DATABASE integration OWNER integration;"
```

```bash
curl -s http://localhost:8081/health
curl -s -X POST http://localhost:8082/sync/coa -H "X-Api-Key: integration-key" | jq .
```

## Part B — Fineract tenant setup

After Fineract is up and CoA sync has created GLs:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r scripts/requirements.txt
PYTHONPATH=scripts python scripts/fineract_setup_part_b.py --out evidence/01-part-b-setup.json
PYTHONPATH=scripts python -m pytest scripts/tests -q
```

Creates (idempotent): office **Kigali**, currency **RWF**, product **SME Asset Finance** (18% p.a., 12 months, cash GL mappings), role/user **assessment-api** / **assessment.api**.

Scenario notes: `evidence/00-STEP0-scenarios.txt`, `evidence/01-STEP1-scenarios.txt`.

## Evidence simulations

See `SIMULATIONS.md` and `API.md`. From this directory (stack up):

```bash
make test
make simulate-lifecycle      # D
make simulate-idempotency    # F
make simulate-concurrency    # I
make simulate-timeout        # J timeout→lookup
make simulate-j-suite        # J ERP-down / recover / Fineract-down
make simulate-reconcile      # K four outcomes
make simulate-coa            # CoA double-run
```

Checklist: `evidence/VERIFICATION_CHECKLIST.txt`. AI disclosure: `AI_USAGE.md`.

Postman: `postman/collection.json` + `postman/environment.json` (see `postman/README.md`).

## Apply Fineract patches locally

```bash
git clone https://github.com/apache/fineract.git fineract-src
cd fineract-src && git checkout 1.16.1
git am /path/to/fineract-assessment/fineract-customization/patches/*.patch
```
