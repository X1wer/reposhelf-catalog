# SPDX-FileCopyrightText: 2026 RepoShelf contributors
# SPDX-License-Identifier: Apache-2.0
"""A build_catalog.py tesztjei. Futtatás a repó gyökeréből: python -m unittest discover -s tools"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build_catalog as bc  # noqa: E402

CATEGORIES = {"games", "system", "other"}


def entry(**overrides):
    base = {
        "id": "demo-app",
        "name": "Demo App",
        "source": {"provider": "github", "repository": "owner/demo", "repositoryId": 42},
        "keywords": ["demo", "példa"],
        "category": "system",
    }
    base.update(overrides)
    return base


class ValidateEntryTest(unittest.TestCase):
    def test_valid_entry(self):
        self.assertEqual([], bc.validate_entry(entry(), "demo-app.json", CATEGORIES))

    def test_each_rule(self):
        cases = {
            "id": entry(id="Bad ID"),
            "fájlnév": entry(id="other-id"),
            "name": entry(name=""),
            "provider": entry(source={"provider": "gitlab", "repository": "owner/demo"}),
            "repository": entry(source={"provider": "github", "repository": "../etc/passwd"}),
            "repositoryId": entry(source={"provider": "github", "repository": "owner/demo", "repositoryId": True}),
            "packageName": entry(packageName="not a package"),
            "signingCertSha256": entry(signingCertSha256=["ABC"]),
            "minVersionCode": entry(minVersionCode=-1),
            "keywords": entry(keywords=["x" * 41]),
            "category": entry(category="quantum"),
            "assetFilter": entry(assetFilter="([unclosed"),
            "ismeretlen mező": entry(description="nem a katalógusba való"),
        }
        for label, value in cases.items():
            with self.subTest(label):
                filename = "other-id.json" if label != "fájlnév" else "demo-app.json"
                filename = "demo-app.json" if label not in ("id", "fájlnév") else filename
                self.assertTrue(bc.validate_entry(value, filename, CATEGORIES), f"elutasítandó: {label}")


class BuildTest(unittest.TestCase):
    def make_repo(self, entries: dict[str, dict]) -> pathlib.Path:
        root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "apps").mkdir()
        (root / "categories.json").write_text(json.dumps({"categories": sorted(CATEGORIES)}), encoding="utf-8")
        for name, value in entries.items():
            (root / "apps" / name).write_text(json.dumps(value), encoding="utf-8")
        return root

    def test_build_is_sorted_and_deterministic(self):
        root = self.make_repo({
            "b-app.json": entry(id="b-app", source={"provider": "github", "repository": "o/b"}),
            "a-app.json": entry(id="a-app", source={"provider": "github", "repository": "o/a"}),
        })
        entries = bc.load_entries(root)
        when = dt.datetime(2026, 11, 10, tzinfo=dt.timezone.utc)
        first = bc.serialize(bc.build(entries, 3, when, 90))
        second = bc.serialize(bc.build(entries, 3, when, 90))
        self.assertEqual(first, second)
        data = json.loads(first)
        self.assertEqual(["a-app", "b-app"], [a["id"] for a in data["apps"]])
        self.assertEqual("2027-02-08T00:00:00Z", data["expiresAt"])
        self.assertTrue(first.endswith(b"\n") and b"\r" not in first)

    def test_duplicate_repository_is_rejected(self):
        root = self.make_repo({
            "a-app.json": entry(id="a-app", source={"provider": "github", "repository": "Owner/Same"}),
            "b-app.json": entry(id="b-app", source={"provider": "github", "repository": "owner/same"}),
        })
        with self.assertRaises(bc.CatalogError):
            bc.load_entries(root)

    def test_serial_must_increase(self):
        root = self.make_repo({"demo-app.json": entry()})
        self.assertEqual(0, bc.main(["--root", str(root), "--serial", "2"]))
        self.assertEqual(1, bc.main(["--root", str(root), "--serial", "2"]))
        self.assertEqual(0, bc.main(["--root", str(root), "--serial", "3"]))

    def test_real_catalog_entries_are_valid(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        self.assertGreaterEqual(len(bc.load_entries(root)), 5)


if __name__ == "__main__":
    unittest.main()
