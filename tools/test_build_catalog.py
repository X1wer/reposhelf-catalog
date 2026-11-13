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


class ClientConformanceTest(unittest.TestCase):
    """Biztonsági audit (CAT-06): a validátor soha nem lehet megengedőbb a kliensnél."""

    def rejected(self, value, filename="demo-app.json"):
        return bool(bc.validate_entry(value, filename, CATEGORIES))

    def test_trailing_newline_is_not_hidden_by_dollar_anchors(self):
        # A Python `$` + `match` a záró újsort elfogadná; a kliens teljes egyezést vár.
        self.assertTrue(self.rejected(entry(source={"provider": "github", "repository": "owner/demo\n"})))
        self.assertTrue(self.rejected(entry(source={"provider": "github", "repository": "owner\n/demo"})))
        self.assertTrue(self.rejected(entry(signingCertSha256=["a" * 64 + "\n"])))
        self.assertTrue(self.rejected(entry(packageName="com.example.app\n")))
        self.assertTrue(self.rejected(entry(id="demo-app\n"), "demo-app\n.json"))

    def test_invisible_and_control_characters_in_displayed_text(self):
        for hidden in ("‮", "​", "⁦", "\u0085", "\u007f", " ", "", "\ud800", "﻿", "\n"):
            with self.subTest(repr(hidden)):
                self.assertTrue(self.rejected(entry(name=f"Signal{hidden}")))
                self.assertTrue(self.rejected(entry(keywords=[f"chat{hidden}"])))
        self.assertFalse(self.rejected(entry(name="Térkép – offline (béta) 🚀", keywords=["日本語"])))

    def test_lengths_are_counted_like_the_client_does(self):
        rocket = "\U0001F680"  # egy kódpont, két UTF-16 kódegység
        self.assertEqual(2, bc.utf16_length(rocket))
        self.assertFalse(self.rejected(entry(name=rocket * 50)))
        self.assertTrue(self.rejected(entry(name=rocket * 51)), "a kliens UTF-16 egységben 102 karakternek látja")
        self.assertTrue(self.rejected(entry(keywords=[rocket * 21])))

    def test_integers_fit_the_client(self):
        big = 1 << 63
        self.assertTrue(self.rejected(entry(source={"provider": "github", "repository": "owner/demo", "repositoryId": big})))
        self.assertTrue(self.rejected(entry(packageName="com.example.app", minVersionCode=big)))
        self.assertFalse(self.rejected(entry(packageName="com.example.app", minVersionCode=big - 1)))

    def test_windows_reserved_ids(self):
        for reserved in ("con", "aux", "nul", "com1", "lpt9", "aux.app"):
            with self.subTest(reserved):
                self.assertTrue(self.rejected(entry(id=reserved), f"{reserved}.json"))
        self.assertFalse(self.rejected(entry(id="console"), "console.json"))


class AssetFilterTest(unittest.TestCase):
    """CAT-02: ugyanaz a korlátos futási idejű részhalmaz, mint a kliensben (AssetFilterSyntax; a listák egyeznek a
    kliens UntrustedTextTest tesztjével)."""

    ACCEPTED = [
        r"^KeePassDX-.*-libre\.apk$",
        r"^app-release-universal\.apk$",
        r"^(?!.*fdroid).*\.apk$",
        r"^cardduel-.*\.apk$",
        r"^NewPipe_v[0-9.]+\.apk$",
        r"^app-(arm64-v8a|armeabi-v7a|x86_64|x86|universal)-release\.apk$",
        r"arm64.*release",
        r"^[A-Za-z]+-[0-9.]+-release\.apk$",
        r"^app-\d\d?\.\d\d?-release\.apk$",
        r"^app[-_]?(?:foss|libre)\.apk$",
        r"^[^-]+-[\w.]+\.apk$",
    ]
    REJECTED = [
        r"(a+)+$", r"^(app-?)+release\.apk$", r"^(a|a)*$", r"^(.*a){10}$", r"^a{1,50}$", r"^(a)\1$", r"(?<=a)b",
        r"(?<name>a)", r"(?P<name>a)", r"(?i)abc", r"(?>a+)b", r"^.*?a$", r"^.*+a$", r"^a**$", r"^[a[b]]$",
        r"^[a-z&&[^b]]$", r"^\p{L}+$", r"^\x41$", r"^.*a.*b.*c$", r"^app-\d+\.\d+\.\d+-release\.apk$",
        r"^app(?:-foss)?\.apk$", r".*a.*b", r"^a|.*b.*c$", "^" + "a?" * 23 + "$", "^(" + "a|" * 23 + "b)$",
        "^abc(", "^abc)", "^[abc$", "^abc\\", "*abc", "^(*a)$", "", "a" * 201, "^a\x00b$", "^térkép\\.apk$",
    ]

    def test_usual_patterns_are_accepted(self):
        for pattern in self.ACCEPTED:
            with self.subTest(pattern):
                self.assertIsNone(bc.asset_filter_violation(pattern))
                self.assertEqual([], bc.validate_entry(entry(assetFilter=pattern), "demo-app.json", CATEGORIES))

    def test_unbounded_patterns_are_rejected(self):
        for pattern in self.REJECTED:
            with self.subTest(pattern):
                self.assertIsNotNone(bc.asset_filter_violation(pattern))
                self.assertTrue(bc.validate_entry(entry(assetFilter=pattern), "demo-app.json", CATEGORIES))

    def test_real_catalog_filters_are_within_the_subset(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        filters = [e["assetFilter"] for e in bc.load_entries(root) if "assetFilter" in e]
        self.assertTrue(filters)
        for pattern in filters:
            self.assertIsNone(bc.asset_filter_violation(pattern), pattern)


class HardeningTest(BuildTest):
    """CAT-03, CAT-04, CAT-12: korlátok és a jóváhagyót megtévesztő bemenetek."""

    def test_duplicate_json_keys_are_rejected(self):
        root = self.make_repo({})
        # A jóváhagyó az első `source`-t olvasná, a feldolgozó az utolsót használná.
        text = ('{"id":"demo-app","name":"Demo","source":{"provider":"github","repository":"good/repo"},'
                '"source":{"provider":"github","repository":"evil/repo"},"category":"system"}')
        (root / "apps" / "demo-app.json").write_text(text, encoding="utf-8")
        with self.assertRaises(bc.CatalogError) as raised:
            bc.load_entries(root)
        self.assertIn("ismétlődő kulcs", str(raised.exception))

    def test_symlinked_entry_is_rejected(self):
        root = self.make_repo({"demo-app.json": entry()})
        outside = root / "outside.json"
        outside.write_text(json.dumps(entry(id="linked", source={"provider": "github", "repository": "o/linked"})), encoding="utf-8")
        try:
            (root / "apps" / "linked.json").symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("ezen a rendszeren nem hozható létre szimbolikus link")
        with self.assertRaises(bc.CatalogError):
            bc.load_entries(root)

    def test_serial_validity_and_empty_catalog_limits(self):
        when = dt.datetime(2026, 11, 10, tzinfo=dt.timezone.utc)
        one = [entry()]
        bc.build(one, bc.MAX_SERIAL, when, bc.MAX_VALIDITY_DAYS)
        for serial, days, entries in ((bc.MAX_SERIAL + 1, 90, one), (0, 90, one), (1, bc.MAX_VALIDITY_DAYS + 1, one), (1, 0, one), (1, 90, [])):
            with self.subTest(serial=serial, days=days, count=len(entries)):
                with self.assertRaises(bc.CatalogError):
                    bc.build(entries, serial, when, days)

    def test_serial_cannot_jump_by_a_typo(self):
        root = self.make_repo({"demo-app.json": entry()})
        self.assertEqual(0, bc.main(["--root", str(root), "--serial", "5"]))
        self.assertEqual(1, bc.main(["--root", str(root), "--serial", "5000000"]))
        self.assertEqual(0, bc.main(["--root", str(root), "--serial", "1005"]))


if __name__ == "__main__":
    unittest.main()
