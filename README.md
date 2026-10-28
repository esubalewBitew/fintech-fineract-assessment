# fineract-assessment

Take-home assessment: Apache Fineract GL `externalReference` customization + Integration Service / Mock ERP (Python).

Pinned Fineract tag: `1.16.1`

## Layout

- `fineract-customization/patches/` — patch series against Apache Fineract `1.16.1` (apply with `git am` on a clean tag checkout)
- `fineract-customization/Dockerfile` — builds a local `fineract:assessment` image with those patches applied
- `config/docker/` — env + PostgreSQL init copied from upstream Fineract docker layout
- `docker-compose.yml` — PostgreSQL + patched Fineract (upstream compose pattern; custom image)
- More folders (`integration-service/`, `mock-erp/`, docs) will be added as work progresses.

## Apply Fineract patches

```bash
git clone https://github.com/apache/fineract.git fineract-src
cd fineract-src
git checkout 1.16.1
git am /path/to/fineract-assessment/fineract-customization/patches/*.patch
```

## Run with Docker

```bash
cd fineract-assessment
docker compose build fineract   # first build is long (clones Fineract + Gradle)
docker compose up -d
# HTTPS on https://localhost:8443
```
