########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
#########################################################################

SHELL = /bin/sh

APP_NAME := $(shell grep ^APP_NAME web/branding.py | awk -F"=" '{print $$NF}' | tr -d '[:space:]' | tr -d "'" | awk '{print tolower($$0)}')
APP_RELEASE := $(shell grep ^APP_RELEASE web/version.py | awk -F"=" '{print $$NF}' | tr -d '[:space:]')
APP_REVISION := $(shell grep ^APP_REVISION web/version.py | awk -F"=" '{print $$NF}' | tr -d '[:space:]')

#########################################################################
# High-level targets
#########################################################################

help:
	@echo "Setup and build:"
	@echo "  all                   docs, pip and src packages (platform-independent)"
	@echo "  install-node          install web/ Node dependencies (yarn install)"
	@echo "  install-python        create the Python environment"
	@echo "  install-python-testing  Python environment incl. test requirements"
	@echo "  bundle                production web bundle"
	@echo "  bundle-dev            development web bundle"
	@echo "  appbundle             macOS application bundle (BUILD_OPTS to pass args)"
	@echo "Checks:"
	@echo "  check                 full gate: install, bundle, lint, check-gates, Jest + regression"
	@echo "  check-gates           CDEadmin gates/tests only; no install/lint/Jest/regression"
	@echo "  check-pep8            pycodestyle over docs/, pkg/, web/, tools/"
	@echo "  check-python          Python regression suite (no feature tests)"
	@echo "  check-resql           resql regression suite"
	@echo "  check-feature         feature test suite (installs node, builds bundle)"
	@echo "  check-js              Jest suite (installs node, lints)"
	@echo "  check-js-coverage     Jest suite with coverage"
	@echo "  check-audit           yarn audit"
	@echo "  check-auditjs         auditjs, dependencies group only"
	@echo "  check-auditjs-html    auditjs HTML report"
	@echo "  check-auditpy         Python dependency audit"
	@echo "  ui-descriptors-check  validate ui_descriptors and run family tests"
	@echo "CDEadmin gates and tests:"
	@echo "  cdeadmin-*-test       unit test suites (endpoint-persistence, provider-registry,"
	@echo "                        postgresql/mongodb/redis-provider, resource-explorer,"
	@echo "                        data-studio, result-renderer, semantic-model, operation-bus,"
	@echo "                        security-isolation, quality-infrastructure, product-identity,"
	@echo "                        profile-migration, transport-foundations, actual-engine-pilots,"
	@echo "                        relational-driver-verification, reference-corpus, parity,"
	@echo "                        workspace-shell, scratchbird-consumer, upstream-acceptance,"
	@echo "                        baseline, jest-contract)"
	@echo "  cdeadmin-*-gate       structural gates (architecture, transport, actual-engine,"
	@echo "                        reference-corpus, parity, workspace-shell,"
	@echo "                        scratchbird-consumer, upstream-acceptance, quality,"
	@echo "                        bundle-regression; *-donor-gate variants need CDEADMIN_DONOR_ROOT)"
	@echo "  cdeadmin-*-check      contract/product-identity check targets"
	@echo "  cdeadmin-*-coverage   coverage runs (shared recipe; 75-80% floors)"
	@echo "  cdeadmin-semantic-live  per-engine live semantic verification, ENGINE=duckdb default"
	@echo "                        (aliases: cdeadmin-semantic-live-duckdb, -sqlite)"
	@echo "  cdeadmin-contracts-generate  regenerate provider contracts"
	@echo "  cdeadmin-baseline     read-only baseline (needs CDEADMIN_BASELINE_OUTPUT)"
	@echo "  cdeadmin-branding-inventory  branding report (needs CDEADMIN_BRANDING_OUTPUT)"
	@echo "  cdeadmin-dependency-licenses  license report (needs CDEADMIN_LICENSE_OUTPUT,"
	@echo "                        CDEADMIN_BASELINE_ID)"
	@echo "Packaging and docs:"
	@echo "  docs / docs-pdf / docs-epub  Sphinx documentation"
	@echo "  pip / redhat / debian / src / docker  package builds"
	@echo "  messages              msg-extract + msg-update + msg-compile"
	@echo "Cleaning:"
	@echo "  clean                 all clean-* targets plus generated js/css"
	@echo "  clean-<part>          appbundle, debian, dist, docs, node, pip, redhat, src"

# Include only platform-independent builds in all
all: docs pip src

# Add BUILD_OPTS variable to pass arguments
appbundle:
	./pkg/mac/build.sh $(BUILD_OPTS)

install-node:
	cd web && yarn install

install-python:
	./tools/setup-python-env.sh

install-python-testing:
	./tools/setup-python-env.sh --test

bundle:
	cd web && yarn run bundle

bundle-dev:
	cd web && yarn run bundle:dev

linter:
	cd web && yarn run linter

CHECK_GATES := cdeadmin-contracts-check cdeadmin-architecture-gate ui-descriptors-check \
	cdeadmin-endpoint-persistence-test cdeadmin-provider-registry-test \
	cdeadmin-postgresql-provider-test cdeadmin-mongodb-provider-test \
	cdeadmin-resource-explorer-test cdeadmin-data-studio-test \
	cdeadmin-result-renderer-test cdeadmin-semantic-model-test \
	cdeadmin-operation-bus-test cdeadmin-security-isolation-test \
	cdeadmin-quality-infrastructure-test cdeadmin-product-identity-test \
	cdeadmin-product-identity-check cdeadmin-profile-migration-test \
	cdeadmin-transport-foundations-test cdeadmin-transport-gate \
	cdeadmin-actual-engine-pilots-test cdeadmin-actual-engine-gate \
	cdeadmin-reference-corpus-test cdeadmin-reference-corpus-gate \
	cdeadmin-parity-test cdeadmin-parity-gate \
	cdeadmin-workspace-shell-test cdeadmin-workspace-shell-gate \
	cdeadmin-scratchbird-consumer-test cdeadmin-scratchbird-consumer-gate \
	cdeadmin-upstream-acceptance-test cdeadmin-upstream-acceptance-gate \
	cdeadmin-quality-gate cdeadmin-bundle-regression-gate

# CDEadmin gate/test targets only: no install/bundle/lint, no Jest or
# regression suites. Fast pre-commit check.
check-gates: $(CHECK_GATES)

check: install-node bundle linter check-pep8 check-gates
	cd web && yarn run test:js-once && python regression/runtests.py

check-audit:
	cd web && yarn run audit

check-auditjs:
# Commented the below line to avoid vulnerability in decompress package and
# audit only dependencies folder. Refer https://www.npmjs.com/advisories/1217.
# Pull request is already been send https://github.com/kevva/decompress/pull/73,
# once fixed we will uncomment it.
#	cd web && yarn run auditjs
	cd web && yarn run auditjs --groups dependencies

check-auditjs-html:
	cd web && yarn run auditjs-html

check-auditpy:
	cd web && yarn run auditpy

check-pep8:
	pycodestyle --config=.pycodestyle docs/
	pycodestyle --config=.pycodestyle pkg/
	pycodestyle --config=.pycodestyle web/
	pycodestyle --config=.pycodestyle tools/

check-python:
	cd web && python regression/runtests.py --exclude feature_tests

check-resql:
	cd web && python regression/runtests.py --pkg resql --exclude feature_tests

check-feature: install-node bundle
	cd web && python regression/runtests.py --pkg feature_tests

check-js: install-node linter
	cd web && yarn run test:js-once

check-js-coverage:
	cd web && yarn run test:js-coverage

# Capture a read-only CDEadmin preparation baseline. The output directory is
# deliberately required and must be outside this source tree.
cdeadmin-baseline:
	@test -n "$(CDEADMIN_BASELINE_OUTPUT)" || { echo "CDEADMIN_BASELINE_OUTPUT is required"; exit 2; }
	python3 tools/cdeadmin_baseline.py --source . \
		--output "$(CDEADMIN_BASELINE_OUTPUT)" --require-clean

cdeadmin-baseline-test:
	python3 -m unittest discover -s tools/tests -p 'test_cdeadmin_*.py'

ui-descriptors-check:
	python3 tools/validate_ui_descriptors.py --counts --enforce-counts tools/ui_lint_maximums.json
	python3 -m pytest -q -p no:cacheprovider tools/tests/test_ui_descriptor_service.py tools/tests/test_ui_descriptor_tools.py tools/tests/test_ui_descriptor_postgresql_schema_ids.py tools/tests/test_ui_descriptor_roundtrip_sqlite.py tools/tests/test_ui_descriptor_roundtrip_duckdb.py tools/tests/test_ui_descriptor_operations_sqlite.py tools/tests/test_ui_descriptor_operations_duckdb.py tools/tests/test_ui_descriptor_roundtrip_firebird.py tools/tests/test_ui_descriptor_roundtrip_mariadb.py tools/tests/test_ui_descriptor_server_forms.py

cdeadmin-architecture-gate:
	python3 tools/cdeadmin_architecture_gate.py --source . \
		--policy tools/cdeadmin_architecture_policy.json

cdeadmin-contracts-generate:
	python3 tools/cdeadmin_generate_contracts.py

cdeadmin-contracts-check:
	python3 tools/cdeadmin_generate_contracts.py --check
	python3 tools/cdeadmin_contract_kit.py \
		--manifest tools/tests/fixtures/cdeadmin_contracts/postgresql/provider_manifest.json
	python3 tools/cdeadmin_contract_kit.py \
		--manifest tools/tests/fixtures/cdeadmin_contracts/fixture/provider_manifest.json
	python3 tools/cdeadmin_contract_kit.py \
		--manifest web/pgadmin/cdeadmin/providers/postgresql/provider_manifest.json
	python3 tools/cdeadmin_provider_testkit.py \
		--manifest tools/tests/fixtures/cdeadmin_contracts/fixture/provider_manifest.json \
		--provider tools/tests/fixtures/cdeadmin_contracts/fixture/provider.py \
		--deny-network

cdeadmin-endpoint-persistence-test:
	python3 -m unittest tools.tests.test_cdeadmin_endpoint_persistence -v

cdeadmin-provider-registry-test:
	python3 -m unittest tools.tests.test_cdeadmin_provider_registry -v

cdeadmin-postgresql-provider-test:
	python3 -m unittest tools.tests.test_cdeadmin_postgresql_provider -v

cdeadmin-mongodb-provider-test:
	python3 -m unittest \
		tools.tests.test_cdeadmin_mongodb_provider \
		tools.tests.test_cdeadmin_provider_tooling -v

cdeadmin-redis-provider-test:
	python3 -m unittest \
		tools.tests.test_cdeadmin_redis_provider \
		tools.tests.test_cdeadmin_provider_tooling \
		tools.tests.test_cdeadmin_actual_engine_pilots -v

cdeadmin-resource-explorer-test:
	python3 -m unittest tools.tests.test_cdeadmin_resource_explorer -v

cdeadmin-data-studio-test:
	python3 -m unittest tools.tests.test_cdeadmin_data_studio -v

cdeadmin-result-renderer-test:
	python3 -m unittest tools.tests.test_cdeadmin_result_renderers -v

cdeadmin-semantic-model-test:
	python3 -m unittest \
		tools.tests.test_cdeadmin_semantic_models \
		tools.tests.test_cdeadmin_provider_workspace \
		tools.tests.test_cdeadmin_result_renderers -v

# Per-engine live semantic verification: make cdeadmin-semantic-live ENGINE=sqlite
ENGINE ?= duckdb
cdeadmin-semantic-live:
	python3 tools/cdeadmin_relational_provider_live_verify.py \
		--engine $(ENGINE) \
		--output /tmp/cdeadmin-semantic-live-$(ENGINE).json

cdeadmin-semantic-live-duckdb:
	$(MAKE) cdeadmin-semantic-live ENGINE=duckdb

cdeadmin-semantic-live-sqlite:
	$(MAKE) cdeadmin-semantic-live ENGINE=sqlite

cdeadmin-operation-bus-test:
	python3 -m unittest tools.tests.test_cdeadmin_operation_bus -v

cdeadmin-security-isolation-test:
	python3 -m unittest tools.tests.test_cdeadmin_security_isolation -v

cdeadmin-quality-infrastructure-test:
	python3 -m unittest tools.tests.test_cdeadmin_quality_infrastructure -v

cdeadmin-product-identity-test:
	python3 -m unittest tools.tests.test_cdeadmin_product_identity -v

cdeadmin-product-identity-check:
	python3 tools/cdeadmin_product_identity.py --source . \
		--policy tools/cdeadmin_product_identity_policy.json

# Shared recipe for the cdeadmin *-coverage targets. $1 is the coverage
# data-file stem, $2 the unittest module, $3 the --fail-under percent; each
# target sets COV_INCLUDE to its --include globs.
define coverage_run
rm -f /tmp/$1_coverage
python3 -m coverage run \
	--data-file=/tmp/$1_coverage \
	--include='$(COV_INCLUDE)' \
	-m unittest $2
python3 -m coverage report \
	--data-file=/tmp/$1_coverage \
	--include='$(COV_INCLUDE)' \
	--fail-under=$3
rm -f /tmp/$1_coverage
endef

cdeadmin-product-identity-coverage: COV_INCLUDE = */tools/cdeadmin_product_identity.py,*/web/pgadmin/cdeadmin/product/*.py
cdeadmin-product-identity-coverage:
	$(call coverage_run,cdeadmin_product_identity,tools.tests.test_cdeadmin_product_identity,75)

cdeadmin-branding-inventory:
	@test -n "$(CDEADMIN_BRANDING_OUTPUT)" || { echo "CDEADMIN_BRANDING_OUTPUT is required"; exit 2; }
	python3 tools/cdeadmin_product_identity.py --source . \
		--policy tools/cdeadmin_product_identity_policy.json \
		--output "$(CDEADMIN_BRANDING_OUTPUT)"

cdeadmin-profile-migration-test:
	python3 -m unittest tools.tests.test_cdeadmin_profile_migration -v

cdeadmin-profile-migration-coverage: COV_INCLUDE = */web/pgadmin/cdeadmin/migration/*.py,*/web/migrations/versions/cde_profile_migration_v1_.py
cdeadmin-profile-migration-coverage:
	$(call coverage_run,cdeadmin_profile_migration,tools.tests.test_cdeadmin_profile_migration,80)

cdeadmin-transport-foundations-test:
	python3 -m unittest \
		tools.tests.test_cdeadmin_transport_foundations -v

cdeadmin-transport-gate:
	python3 tools/cdeadmin_transport_gate.py --source .

cdeadmin-transport-coverage: COV_INCLUDE = */web/pgadmin/cdeadmin/transports/*.py,*/tools/cdeadmin_transport_gate.py
cdeadmin-transport-coverage:
	$(call coverage_run,cdeadmin_transport,tools.tests.test_cdeadmin_transport_foundations,80)

cdeadmin-actual-engine-pilots-test:
	python3 -m unittest \
		tools.tests.test_cdeadmin_actual_engine_pilots -v

cdeadmin-relational-driver-verification-test:
	python3 -m unittest \
		tools.tests.test_cdeadmin_relational_driver_verify -v

cdeadmin-relational-driver-verification:
	python3 tools/cdeadmin_relational_driver_verify.py --engine all

cdeadmin-actual-engine-gate:
	python3 tools/cdeadmin_actual_engine_gate.py --source .

cdeadmin-actual-engine-donor-gate:
	@test -n "$(CDEADMIN_DONOR_ROOT)" || { echo "CDEADMIN_DONOR_ROOT is required"; exit 2; }
	python3 tools/cdeadmin_actual_engine_gate.py --source . \
		--donor-root "$(CDEADMIN_DONOR_ROOT)"

cdeadmin-actual-engine-coverage: COV_INCLUDE = */web/pgadmin/cdeadmin/sdk/*.py,*/web/pgadmin/cdeadmin/providers/mysql_family/*.py,*/web/pgadmin/cdeadmin/providers/mongodb/*.py,*/web/pgadmin/cdeadmin/providers/neo4j/*.py,*/web/pgadmin/cdeadmin/providers/clickhouse/*.py,*/web/pgadmin/cdeadmin/providers/duckdb/*.py,*/tools/cdeadmin_actual_engine_gate.py
cdeadmin-actual-engine-coverage:
	$(call coverage_run,cdeadmin_actual_engine,tools.tests.test_cdeadmin_actual_engine_pilots,80)

cdeadmin-reference-corpus-test:
	python3 -m unittest \
		tools.tests.test_cdeadmin_reference_corpus -v

cdeadmin-reference-corpus-gate:
	python3 tools/cdeadmin_reference_corpus.py --source .

cdeadmin-reference-corpus-donor-gate:
	@test -n "$(CDEADMIN_DONOR_ROOT)" || { echo "CDEADMIN_DONOR_ROOT is required"; exit 2; }
	python3 tools/cdeadmin_reference_corpus.py --source . \
		--donor-root "$(CDEADMIN_DONOR_ROOT)"

cdeadmin-reference-corpus-coverage: COV_INCLUDE = */tools/cdeadmin_reference_corpus.py
cdeadmin-reference-corpus-coverage:
	$(call coverage_run,cdeadmin_reference_corpus,tools.tests.test_cdeadmin_reference_corpus,80)

cdeadmin-parity-test:
	python3 -m unittest \
		tools.tests.test_cdeadmin_parity_runner -v

cdeadmin-parity-gate:
	python3 tools/cdeadmin_parity_runner.py --source .

cdeadmin-parity-reference-gate:
	python3 tools/cdeadmin_parity_runner.py --source . \
		--require-reference-complete

cdeadmin-parity-release-gate:
	python3 tools/cdeadmin_parity_runner.py --source . --require-release

cdeadmin-parity-coverage: COV_INCLUDE = */tools/cdeadmin_parity_runner.py
cdeadmin-parity-coverage:
	$(call coverage_run,cdeadmin_parity,tools.tests.test_cdeadmin_parity_runner,75)

cdeadmin-workspace-shell-test:
	python3 -m unittest \
		tools.tests.test_cdeadmin_workspace_shells -v

cdeadmin-workspace-shell-gate:
	python3 tools/cdeadmin_workspace_shell_gate.py --source .

cdeadmin-workspace-shell-coverage: COV_INCLUDE = */tools/cdeadmin_workspace_shell_gate.py
cdeadmin-workspace-shell-coverage:
	$(call coverage_run,cdeadmin_workspace_shell,tools.tests.test_cdeadmin_workspace_shells,80)

cdeadmin-scratchbird-consumer-test:
	python3 -m unittest \
		tools.tests.test_cdeadmin_scratchbird_consumer -v

cdeadmin-scratchbird-consumer-gate:
	python3 tools/cdeadmin_scratchbird_consumer.py --source .

cdeadmin-scratchbird-consumer-coverage: COV_INCLUDE = */tools/cdeadmin_scratchbird_consumer.py
cdeadmin-scratchbird-consumer-coverage:
	$(call coverage_run,cdeadmin_scratchbird_consumer,tools.tests.test_cdeadmin_scratchbird_consumer,80)

cdeadmin-upstream-acceptance-test:
	python3 -m unittest \
		tools.tests.test_cdeadmin_upstream_acceptance -v

cdeadmin-upstream-acceptance-gate:
	python3 tools/cdeadmin_upstream_acceptance.py --source .

cdeadmin-upstream-acceptance-coverage: COV_INCLUDE = */tools/cdeadmin_upstream_acceptance.py
cdeadmin-upstream-acceptance-coverage:
	$(call coverage_run,cdeadmin_upstream_acceptance,tools.tests.test_cdeadmin_upstream_acceptance,80)

cdeadmin-quality-gate:
	python3 tools/cdeadmin_quality_gate.py --source . \
		--policy tools/cdeadmin_quality_policy.json

cdeadmin-bundle-regression-gate:
	python3 tools/cdeadmin_quality_gate.py --source . \
		--policy tools/cdeadmin_quality_policy.json \
		--require-built-bundle

cdeadmin-quality-coverage: COV_INCLUDE = */tools/cdeadmin_provider_testkit.py,*/tools/cdeadmin_quality_gate.py
cdeadmin-quality-coverage:
	$(call coverage_run,cdeadmin_quality,tools.tests.test_cdeadmin_quality_infrastructure,75)

cdeadmin-jest-contract-test:
	cd web && corepack yarn run jest --runInBand \
		regression/javascript/cdeadmin/ContractCompatibility.spec.js

cdeadmin-jest-contract-coverage:
	cd web && corepack yarn run jest --runInBand --coverage \
		--collectCoverageFrom='pgadmin/cdeadmin/static/js/contracts/v1/generated.ts' \
		--coverageReporters=text-summary \
		--coverageThreshold='{"global":{"lines":90,"statements":90}}' \
		regression/javascript/cdeadmin/ContractCompatibility.spec.js

cdeadmin-dependency-licenses:
	@test -n "$(CDEADMIN_LICENSE_OUTPUT)" || { echo "CDEADMIN_LICENSE_OUTPUT is required"; exit 2; }
	@test -n "$(CDEADMIN_BASELINE_ID)" || { echo "CDEADMIN_BASELINE_ID is required"; exit 2; }
	python3 tools/cdeadmin_dependency_licenses.py \
		--output "$(CDEADMIN_LICENSE_OUTPUT)" \
		--baseline-id "$(CDEADMIN_BASELINE_ID)" \
		$(foreach root,$(CDEADMIN_NODE_ROOTS),--node-root "$(root)")

# Include all clean sub-targets in clean
clean: clean-appbundle clean-debian clean-dist clean-docs clean-node clean-pip clean-redhat clean-src
	rm -rf web/pgadmin/static/js/generated/*
	rm -rf web/pgadmin/static/js/generated/.cache
	rm -rf web/pgadmin/static/css/generated/*
	rm -rf web/pgadmin/static/css/generated/.cache

clean-appbundle:
	rm -rf mac-build/

clean-debian:
	rm -rf debian-build/

clean-dist:
	rm -rf dist/

clean-docs:
	LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 $(MAKE) -C docs/en_US -f Makefile.sphinx clean

clean-node:
	rm -rf web/node_modules/

clean-pip:
	rm -rf pip-build/

clean-redhat:
	rm -rf redhat-build/

clean-src:
	rm -rf src-build/

debian:
	./pkg/debian/build.sh

docker:
	echo $(APP_NAME)
	docker build --pull -t ${APP_NAME} -t $(APP_NAME):latest -t $(APP_NAME):$(APP_RELEASE) -t $(APP_NAME):$(APP_RELEASE).$(APP_REVISION) .

docs:
	LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 $(MAKE) -C docs/en_US -f Makefile.sphinx html

docs-pdf:
	LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 $(MAKE) -C docs/en_US -f Makefile.sphinx latexpdf

docs-epub:
	LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 $(MAKE) -C docs/en_US -f Makefile.sphinx epub

messages: msg-extract msg-update msg-compile

msg-compile:
	cd web && pybabel compile --statistics -d pgadmin/translations

msg-extract:
	cd web && pybabel extract -F babel.cfg -o pgadmin/messages.pot pgadmin

msg-update:
	cd web && pybabel update --no-fuzzy-matching -i pgadmin/messages.pot -d pgadmin/translations

.PHONY: all appbundle install-node install-python install-python-testing \
	bundle bundle-dev linter help \
	check check-gates check-audit check-auditjs check-auditjs-html \
	check-auditpy check-pep8 check-python check-resql check-feature \
	check-js check-js-coverage ui-descriptors-check \
	cdeadmin-baseline cdeadmin-baseline-test cdeadmin-architecture-gate \
	cdeadmin-dependency-licenses cdeadmin-contracts-generate \
	cdeadmin-contracts-check cdeadmin-endpoint-persistence-test \
	cdeadmin-provider-registry-test cdeadmin-postgresql-provider-test \
	cdeadmin-mongodb-provider-test cdeadmin-redis-provider-test \
	cdeadmin-resource-explorer-test cdeadmin-data-studio-test \
	cdeadmin-result-renderer-test cdeadmin-semantic-model-test \
	cdeadmin-semantic-live cdeadmin-semantic-live-duckdb \
	cdeadmin-semantic-live-sqlite cdeadmin-operation-bus-test \
	cdeadmin-security-isolation-test cdeadmin-quality-infrastructure-test \
	cdeadmin-product-identity-test cdeadmin-product-identity-check \
	cdeadmin-product-identity-coverage cdeadmin-branding-inventory \
	cdeadmin-profile-migration-test cdeadmin-profile-migration-coverage \
	cdeadmin-transport-foundations-test cdeadmin-transport-gate \
	cdeadmin-transport-coverage cdeadmin-actual-engine-pilots-test \
	cdeadmin-relational-driver-verification-test \
	cdeadmin-relational-driver-verification cdeadmin-actual-engine-gate \
	cdeadmin-actual-engine-donor-gate cdeadmin-actual-engine-coverage \
	cdeadmin-reference-corpus-test cdeadmin-reference-corpus-gate \
	cdeadmin-reference-corpus-donor-gate cdeadmin-reference-corpus-coverage \
	cdeadmin-parity-test cdeadmin-parity-gate \
	cdeadmin-parity-reference-gate cdeadmin-parity-release-gate \
	cdeadmin-parity-coverage cdeadmin-workspace-shell-test \
	cdeadmin-workspace-shell-gate cdeadmin-workspace-shell-coverage \
	cdeadmin-scratchbird-consumer-test cdeadmin-scratchbird-consumer-gate \
	cdeadmin-scratchbird-consumer-coverage \
	cdeadmin-upstream-acceptance-test cdeadmin-upstream-acceptance-gate \
	cdeadmin-upstream-acceptance-coverage cdeadmin-quality-gate \
	cdeadmin-bundle-regression-gate cdeadmin-quality-coverage \
	cdeadmin-jest-contract-test cdeadmin-jest-contract-coverage \
	clean clean-appbundle clean-debian clean-dist clean-docs clean-node \
	clean-pip clean-redhat clean-src debian docker docs docs-pdf \
	docs-epub messages msg-compile msg-extract msg-update pip redhat src

pip: docs
	./pkg/pip/build.sh

redhat:
	./pkg/redhat/build.sh

src:
	./pkg/src/build.sh
