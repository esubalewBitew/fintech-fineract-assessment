# Assessment helpers — run from fineract-assessment/
.PHONY: help up down ps test test-integration test-mock-erp setup-part-b sync-coa \
	simulate-coa simulate-lifecycle simulate-concurrency simulate-timeout simulate-reconcile evidence

COMPOSE ?= docker compose
INT_KEY ?= integration-key

help:
	@echo "Targets:"
	@echo "  up / down / ps          compose stack"
	@echo "  test                    unit tests (integration + mock-erp + scripts)"
	@echo "  sync-coa                POST /sync/coa"
	@echo "  setup-part-b            Part B Fineract bootstrap"
	@echo "  simulate-coa            CoA sync evidence → evidence/11-coa-sync.json"
	@echo "  simulate-lifecycle      Part D → evidence/03-lifecycle.json"
	@echo "  simulate-concurrency    Part I → evidence/07-concurrency.json"
	@echo "  simulate-timeout        Part J → evidence/08-timeout-lookup.*"
	@echo "  simulate-reconcile      Part K (4 outcomes) — NOT IMPLEMENTED YET"
	@echo "  evidence                list evidence/"

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

test: test-integration test-mock-erp test-scripts

test-integration:
	cd integration-service && PYTHONPATH=. python -m pytest -q

test-mock-erp:
	cd mock-erp && PYTHONPATH=. python -m pytest -q

test-scripts:
	PYTHONPATH=scripts python -m pytest scripts/tests -q

sync-coa:
	curl -s -X POST http://localhost:8082/sync/coa -H "X-Api-Key: $(INT_KEY)" | tee evidence/11-coa-sync.json | python -m json.tool | head -40

setup-part-b:
	PYTHONPATH=scripts python scripts/fineract_setup_part_b.py --out evidence/01-part-b-setup.json

simulate-coa: sync-coa
	@echo "Wrote evidence/11-coa-sync.json"

simulate-lifecycle:
	PYTHONPATH=scripts python scripts/simulate_lifecycle_part_d.py

simulate-concurrency:
	PYTHONPATH=scripts python scripts/simulate_concurrency_part_i.py

simulate-timeout:
	PYTHONPATH=scripts python scripts/simulate_timeout_part_j.py

simulate-reconcile:
	@echo "FAIL: Part K not fully evidenced — need one report with MATCHED/MISSING_IN_ERP/MISSING_IN_FINERACT/AMOUNT_MISMATCH"
	@echo "See GAPS_PLAN.md Step 9. Expected evidence: evidence/09-reconcile-four-outcomes.json"
	@exit 1

evidence:
	@ls -la evidence/
