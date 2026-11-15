##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Verification of developer onboarding docs, Docker catalog and test-DB CLI."""

from __future__ import annotations

import importlib.util
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "tools/reference_engine_demos"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DeveloperOnboardingToolsTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.docker_images = _load("docker_images", DEMO / "docker_images.py")
        cls.create_db = _load(
            "create_test_database", DEMO / "create_test_database.py"
        )
        cls.estate = _load("demo_estate", DEMO / "demo_estate.py")
        cls.bootstrap = _load("bootstrap", DEMO / "bootstrap.py")
        cls.manage = _load(
            "manage_dev", ROOT / "tools/development/manage.py"
        )

    def test_docker_image_catalog_matches_estate_bootstrap_and_vitess(self):
        catalog_images = {
            entry["image"] for entry in self.docker_images.DOCKER_IMAGE_CATALOG
        }
        self.assertEqual(29, len(catalog_images))
        for image in catalog_images:
            self.assertIn(":", image)
            self.assertFalse(image.endswith(":latest"), image)

        # Every standard container image in demo_estate.py is in the catalog.
        for engine, spec in self.estate.CONTAINERS.items():
            self.assertIn(spec["image"], catalog_images, engine)

        # Every client-extraction image in bootstrap.py is marked bootstrap.
        bootstrap_catalog = {
            entry["image"]
            for entry in self.docker_images.DOCKER_IMAGE_CATALOG
            if entry["bootstrap_client"]
        }
        expected_bootstrap = {
            self.bootstrap.FOUNDATIONDB_IMAGE,
            self.bootstrap.FIREBIRD_IMAGE,
            self.bootstrap.MARIADB_IMAGE,
            self.bootstrap.MYSQL_IMAGE,
            self.bootstrap.CASSANDRA_IMAGE,
            self.bootstrap.IGNITE_IMAGE,
            self.bootstrap.YUGABYTE_IMAGE,
        }
        self.assertEqual(expected_bootstrap, bootstrap_catalog)

        # Every image in Vitess docker-compose.yml is in the catalog.
        vitess_compose = (
            DEMO / "config/vitess/docker-compose.yml"
        ).read_text(encoding="utf-8")
        compose_images = set(
            re.findall(r"^\s*image:\s*(\S+)\s*$", vitess_compose, re.MULTILINE)
        )
        self.assertTrue(compose_images.issubset(catalog_images))

    def test_developer_setup_guide_documents_every_pinned_docker_image(self):
        for relative in (
            "docs/DEVELOPER_SETUP.md",
            "docs/AI_AGENT_TEST_ENVIRONMENT_SETUP.md",
        ):
            guide_path = ROOT / relative
            self.assertTrue(guide_path.is_file(), relative)
            guide_text = guide_path.read_text(encoding="utf-8")
            for entry in self.docker_images.DOCKER_IMAGE_CATALOG:
                self.assertIn(
                    f"`{entry['image']}`",
                    guide_text,
                    f"{relative} missing Docker image {entry['image']}",
                )
            self.assertIn("Diagram-Design-Notation.git", guide_text)
            self.assertIn("dev.sh create-db", guide_text)
            self.assertIn("chrome-sandbox", guide_text)

    def test_manage_exposes_images_pull_and_create_db_actions(self):
        for action in ("images", "pull", "create-db"):
            self.assertIn(action, self.manage.ACTIONS)

    def test_pull_images_dry_run_does_not_invoke_docker(self):
        with mock.patch.object(
            self.docker_images.subprocess, "run"
        ) as run_mock:
            pulled = self.docker_images.pull_images("postgresql", dry_run=True)
        self.assertEqual(["postgres:18.3"], pulled)
        run_mock.assert_not_called()

    def test_create_test_database_validates_names_and_protects_canonical_demos(
        self,
    ):
        for invalid in ("", "1bad", "bad-name", "drop;table", "../escape"):
            with self.assertRaises(ValueError):
                self.create_db.validate_database_name(invalid)

        for protected in ("cdeadmin_demo", "test_keyspace", "postgres", "mysql"):
            with self.assertRaises(ValueError):
                self.create_db.validate_database_name(protected)

        dry = self.create_db.create_test_database(
            "postgresql", "dev_isolated_test", seed=True, dry_run=True
        )
        self.assertTrue(dry["dry_run"])
        self.assertEqual("dev_isolated_test", dry["database"])
        self.assertTrue(dry["seed_field_service_fixture"])

    def test_create_test_database_sqlite_seed_and_custom_sql(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sql_file = tmp_path / "extra.sql"
            sql_file.write_text(
                "-- comment line\n"
                "CREATE TABLE extra_notes (id INTEGER PRIMARY KEY, body TEXT);\n"
                "INSERT INTO extra_notes VALUES (1, 'ready');\n",
                encoding="utf-8",
            )
            with mock.patch.object(self.create_db, "DATA", tmp_path), \
                 mock.patch.object(self.create_db, "RUNTIME", tmp_path / "rt"):
                result = self.create_db.create_test_database(
                    "sqlite",
                    "unit_test_isolated_db",
                    seed=True,
                    sql_file=sql_file,
                )
            db_file = Path(result["database"])
            self.assertTrue(db_file.is_file())
            conn = sqlite3.connect(db_file)
            try:
                customers = conn.execute(
                    "SELECT COUNT(*) FROM customers"
                ).fetchone()[0]
                notes = conn.execute(
                    "SELECT body FROM extra_notes WHERE id = 1"
                ).fetchone()[0]
                self.assertEqual(3, customers)
                self.assertEqual("ready", notes)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
