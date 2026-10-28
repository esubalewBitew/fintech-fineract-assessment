# fineract-assessment

Take-home: Apache Fineract GL `externalReference` (patches) + **Integration middleware** + **Mock ERP** ledger (Python).

Pinned Fineract tag: `1.16.1`

## Layout

| Path | Brief |
|------|--------|
| `fineract-customization/patches/` | CBS customization (A) |
| `ARCHITECTURE.md` / `DECISIONS.md` | Design decisions |
| `mock-erp/` | G — ledger with journals |
| `integration-service/` | A-sync, E–K middleware |
| `docker-compose.yml` | Postgres + Fineract + Mock ERP + Integration |
| `INTERVIEW_PREP_PART_A.md` | Fineract interview crib |
| `INTERVIEW_PREP_MIDDLEWARE.md` | Middleware interview crib |

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

Remaining work (B–K scenarios): `GAPS_PLAN.md`.

```bash
curl -s http://localhost:8081/health
curl -s -X POST http://localhost:8082/sync/coa -H "X-Api-Key: integration-key" | jq .
```

## Apply Fineract patches locally

```bash
git clone https://github.com/apache/fineract.git fineract-src
cd fineract-src && git checkout 1.16.1
git am /path/to/fineract-assessment/fineract-customization/patches/*.patch
```
