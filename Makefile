# Assessment helpers — run from fineract-assessment/
.PHONY: help up down ps test test-integration test-mock-erp setup-part-b sync-coa \
	simulate-coa simulate-lifecycle simulate-concurrency simulate-timeout simulate-reconcile \
	simulate-j-suite simulate-idempotency evidence

COMPOSE ?= docker compose
INT_KEY ?= integration-key

help:
	@echo "Targets:"
	@echo "  up / down / ps          compose stack"
	@echo "  test                    unit tests (integration + mock-erp + scripts)"
	@echo "  sync-coa                POST /sync/coa"
	@echo "  setup-part-b            Part B Fineract bootstrap"
	@echo "  simulate-coa            CoA double-run → evidence/11-coa-sync-*.json"
	@echo "  simulate-lifecycle      Part D → evidence/03-lifecycle.json"
	@echo "  simulate-concurrency    Part I → evidence/07-concurrency.json"
	@echo "  simulate-timeout        Part J timeout→lookup → evidence/08-timeout-lookup.*"
	@echo "  simulate-j-suite        Part J ERP-down + recover + Fineract-down → evidence/08-j-suite.json"
	@echo "  simulate-idempotency    Part F matrix → evidence/05-idempotency.*"
	@echo "  simulate-reconcile      Part K → evidence/09-reconcile-four-outcomes.json"
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

simulate-coa:
	PYTHONPATH=scripts python scripts/simulate_coa_double.py

simulate-lifecycle:
	PYTHONPATH=scripts python scripts/simulate_lifecycle_part_d.py

simulate-concurrency:
	PYTHONPATH=scripts python scripts/simulate_concurrency_part_i.py

simulate-timeout:
	PYTHONPATH=scripts python scripts/simulate_timeout_part_j.py

simulate-j-suite:
	PYTHONPATH=scripts python scripts/simulate_failures_part_j.py

simulate-idempotency:
	PYTHONPATH=scripts python scripts/simulate_idempotency_part_f.py

simulate-reconcile:
	PYTHONPATH=scripts python scripts/simulate_reconcile_part_k.py

evidence:
	@ls -la evidence/
