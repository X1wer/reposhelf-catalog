# SPDX-FileCopyrightText: 2026 RepoShelf contributors
# SPDX-License-Identifier: Apache-2.0
"""A validate_catalog.py és a sign_catalog.py tesztjei. A kulcsokat a teszt generálja ideiglenes könyvtárba."""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build_catalog as bc  # noqa: E402
import sign_catalog as sc  # noqa: E402
import validate_catalog as vc  # noqa: E402

OPENSSL = shutil.which("openssl")


def entry(app_id: str, repo: str, **extra) -> dict:
    data = {"id": app_id, "name": app_id.title(), "source": {"provider": "github", "repository": repo}, "category": "system"}
    data.update(extra)
    return data


class Repo:
    """Egy minimális katalógusrepó ideiglenes könyvtárban."""

    def __init__(self, entries: list[dict]):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        (self.root / "apps").mkdir()
        (self.root / "keys").mkdir()
        (self.root / "categories.json").write_text(json.dumps({"categories": ["system", "games"]}), encoding="utf-8")
        for e in entries:
            (self.root / "apps" / f"{e['id']}.json").write_text(json.dumps(e), encoding="utf-8")
        self.build()

    def build(self):
        catalog = bc.build(bc.load_entries(self.root), 1, dt.datetime(2026, 11, 12, tzinfo=dt.timezone.utc), 90)
        out = self.root / "dist" / "v1" / "catalog.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(bc.serialize(catalog))

    def close(self):
        self.tmp.cleanup()


class ContradictionTest(unittest.TestCase):
    def test_reports_shared_package_repo_id_and_meaningless_fields(self):
        entries = [
            entry("a-app", "o/a", packageName="com.example.x", source={"provider": "github", "repository": "o/a", "repositoryId": 7}),
            entry("b-app", "o/b", packageName="com.example.x", source={"provider": "github", "repository": "o/b", "repositoryId": 7}),
            entry("c-app", "o/c", minVersionCode=3, keywords=["Foo", "foo"], signingCertSha256=["a" * 64, "a" * 64]),
        ]
        text = "\n".join(vc.contradictions(entries))
        self.assertIn("packageName (com.example.x) már szerepel", text)
        self.assertIn("repositoryId (7) már szerepel", text)
        self.assertIn("minVersionCode csak packageName mellett", text)
        self.assertIn("ismétlődő kulcsszó", text)
        self.assertIn("ismétlődő signingCertSha256", text)

    def test_consistent_entries_have_no_contradiction(self):
        self.assertEqual([], vc.contradictions([entry("a-app", "o/a"), entry("b-app", "o/b", packageName="com.b", minVersionCode=1)]))


class DistTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo([entry("a-app", "o/a"), entry("b-app", "o/b")])

    def tearDown(self):
        self.repo.close()

    def test_valid_repo_without_signature_passes_unless_required(self):
        problems, notes = vc.validate(self.repo.root, require_signature=False, openssl=OPENSSL or "openssl")
        self.assertEqual([], problems)
        self.assertTrue(any("nincs aláírás" in n for n in notes))
        problems, _ = vc.validate(self.repo.root, require_signature=True, openssl=OPENSSL or "openssl")
        self.assertIn("dist: hiányzik a catalog.json.sig", problems)

    def test_hand_edited_or_inconsistent_dist_is_rejected(self):
        path = self.repo.root / "dist" / "v1" / "catalog.json"
        catalog = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps(catalog), encoding="utf-8")  # nem a determinisztikus forma
        problems, _ = vc.validate_dist(self.repo.root, {"system"})
        self.assertTrue(any("determinisztikus" in p for p in problems))
        catalog["expiresAt"] = catalog["generatedAt"]
        catalog["apps"].append(dict(catalog["apps"][0]))
        path.write_bytes(bc.serialize(catalog))
        text = "\n".join(vc.validate_dist(self.repo.root, {"system"})[0])
        self.assertIn("expiresAt", text)
        self.assertIn("duplikált id", text)

    def test_pending_entry_is_a_note_not_an_error(self):
        (self.repo.root / "apps" / "c-app.json").write_text(json.dumps(entry("c-app", "o/c")), encoding="utf-8")
        problems, notes = vc.validate(self.repo.root, require_signature=False, openssl=OPENSSL or "openssl")
        self.assertEqual([], problems)
        self.assertTrue(any("újragenerálja" in n for n in notes))

    def test_invalid_entry_fails(self):
        (self.repo.root / "apps" / "bad.json").write_text(json.dumps(entry("bad", "not a repo")), encoding="utf-8")
        problems, _ = vc.validate(self.repo.root, require_signature=False, openssl=OPENSSL or "openssl")
        self.assertTrue(any("bad.json" in p for p in problems))


@unittest.skipIf(OPENSSL is None, "nincs openssl")
class SignatureTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo([entry("a-app", "o/a")])
        self.keys = tempfile.TemporaryDirectory()
        self.private = pathlib.Path(self.keys.name) / "test.key"
        subprocess.run([OPENSSL, "ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", str(self.private)], check=True, capture_output=True)
        subprocess.run([OPENSSL, "ec", "-in", str(self.private), "-pubout", "-out", str(self.repo.root / "keys" / "test-key.pub")], check=True, capture_output=True)

    def tearDown(self):
        self.repo.close()
        self.keys.cleanup()

    def test_signed_catalog_verifies(self):
        out = sc.sign(self.repo.root, [("test-key", self.private)], OPENSSL)
        document = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(1, document["format"])
        self.assertEqual("ecdsa-p256-sha256", document["signatures"][0]["algorithm"])
        self.assertEqual(("valid", "test-key"), vc.verify_signature(self.repo.root, OPENSSL))
        self.assertEqual([], vc.validate(self.repo.root, require_signature=True, openssl=OPENSSL)[0])

    def test_tampered_catalog_or_unknown_key_is_invalid(self):
        sc.sign(self.repo.root, [("test-key", self.private)], OPENSSL)
        catalog = self.repo.root / "dist" / "v1" / "catalog.json"
        catalog.write_bytes(catalog.read_bytes().replace(b"A-App", b"B-App"))
        self.assertEqual("invalid", vc.verify_signature(self.repo.root, OPENSSL)[0])
        self.repo.build()
        sc.sign(self.repo.root, [("test-key", self.private)], OPENSSL)
        (self.repo.root / "keys" / "test-key.pub").rename(self.repo.root / "keys" / "other.pub")
        self.assertEqual("invalid", vc.verify_signature(self.repo.root, OPENSSL)[0])

    def test_malformed_signature_file_is_invalid(self):
        (self.repo.root / "dist" / "v1" / "catalog.json.sig").write_text("{nem json", encoding="utf-8")
        self.assertEqual("invalid", vc.verify_signature(self.repo.root, OPENSSL)[0])

    def test_private_key_inside_the_repository_is_refused(self):
        inside = self.repo.root / "keys" / "inside.key"
        shutil.copy(self.private, inside)
        with self.assertRaises(sc.SigningError):
            sc.sign(self.repo.root, [("test-key", inside)], OPENSSL)


class AuditHardeningTest(unittest.TestCase):
    """Biztonsági audit: CAT-03, CAT-04 (dist-korlátok), CAT-08 (aláírás nélküli dist), CAT-12 / CAT-13 (kulcsok, aláírás)."""

    def setUp(self):
        self.repo = Repo([entry("a-app", "o/a")])

    def tearDown(self):
        self.repo.close()

    def rewrite_dist(self, **changes):
        path = self.repo.root / "dist" / "v1" / "catalog.json"
        catalog = json.loads(path.read_text(encoding="utf-8"))
        catalog.update(changes)
        path.write_bytes(bc.serialize(catalog))
        return "\n".join(vc.validate_dist(self.repo.root, {"system"})[0])

    def test_dist_limits_match_the_client(self):
        self.assertEqual("", self.rewrite_dist())
        self.assertIn("catalogSerial", self.rewrite_dist(catalogSerial=bc.MAX_SERIAL + 1))
        self.assertIn("érvényesség", self.rewrite_dist(catalogSerial=1, expiresAt="2028-01-01T00:00:00Z"))
        self.assertIn("2020 és 2100", self.rewrite_dist(generatedAt="1999-01-01T00:00:00Z", expiresAt="1999-03-01T00:00:00Z"))
        self.assertIn("üres apps", self.rewrite_dist(generatedAt="2026-11-12T00:00:00Z", expiresAt="2027-02-10T00:00:00Z", apps=[]))

    def test_dist_with_duplicate_keys_is_rejected(self):
        path = self.repo.root / "dist" / "v1" / "catalog.json"
        path.write_text('{"schemaVersion":1,"schemaVersion":1,"catalogSerial":1,"apps":[]}', encoding="utf-8")
        self.assertIn("hibás JSON", "\n".join(vc.validate_dist(self.repo.root, {"system"})[0]))

    @unittest.skipIf(OPENSSL is None, "nincs openssl")
    def test_only_p256_public_keys_are_trusted(self):
        keys = self.repo.root / "keys"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            good, p384, rsa = tmp_path / "good.key", tmp_path / "p384.key", tmp_path / "rsa.key"
            subprocess.run([OPENSSL, "ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", str(good)], check=True, capture_output=True)
            subprocess.run([OPENSSL, "ecparam", "-name", "secp384r1", "-genkey", "-noout", "-out", str(p384)], check=True, capture_output=True)
            subprocess.run([OPENSSL, "genrsa", "-out", str(rsa), "2048"], check=True, capture_output=True)
            subprocess.run([OPENSSL, "pkey", "-in", str(good), "-pubout", "-out", str(keys / "good-key.pub")], check=True, capture_output=True)
            subprocess.run([OPENSSL, "pkey", "-in", str(p384), "-pubout", "-out", str(keys / "p384-key.pub")], check=True, capture_output=True)
            subprocess.run([OPENSSL, "pkey", "-in", str(rsa), "-pubout", "-out", str(keys / "rsa-key.pub")], check=True, capture_output=True)
            (keys / "garbage.pub").write_text("not a key", encoding="utf-8")
            trusted, problems = vc.trusted_keys(self.repo.root)
            self.assertEqual(["good-key"], sorted(trusted))
            self.assertEqual(3, len(problems))
            self.assertIsNotNone(vc.read_p256_public_key(keys / "good-key.pub"))
            # A hibás kulcsok a validációt is megbuktatják (nem maradhatnak észrevétlenül a repóban).
            self.assertTrue(any("p384-key.pub" in p for p in vc.validate(self.repo.root, require_signature=False, openssl=OPENSSL)[0]))
            # Egy P-384 kulccsal készült (de p256-nak címkézett) aláírás nem érvényes.
            for bad in ("p384-key.pub", "rsa-key.pub", "garbage.pub"):
                (keys / bad).unlink()
            sc.sign(self.repo.root, [("good-key", good)], OPENSSL)
            self.assertEqual(("valid", "good-key"), vc.verify_signature(self.repo.root, OPENSSL))
            with self.assertRaises(sc.SigningError):
                sc.sign(self.repo.root, [("p384-key", p384)], OPENSSL)

    @unittest.skipIf(OPENSSL is None, "nincs openssl")
    def test_signing_refuses_a_dist_that_is_not_built_from_apps(self):
        keys = self.repo.root / "keys"
        with tempfile.TemporaryDirectory() as tmp:
            private, other = pathlib.Path(tmp) / "k.key", pathlib.Path(tmp) / "other.key"
            for key in (private, other):
                subprocess.run([OPENSSL, "ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", str(key)], check=True, capture_output=True)
            # Nincs közzétett nyilvános kulcs ehhez az azonosítóhoz.
            with self.assertRaises(sc.SigningError):
                sc.sign(self.repo.root, [("test-key", private)], OPENSSL)
            subprocess.run([OPENSSL, "pkey", "-in", str(private), "-pubout", "-out", str(keys / "test-key.pub")], check=True, capture_output=True)
            # Más privát kulcs, mint amelynek a nyilvános része a repóban van.
            with self.assertRaises(sc.SigningError):
                sc.sign(self.repo.root, [("test-key", other)], OPENSSL)
            sig = self.repo.root / "dist" / "v1" / "catalog.json.sig"
            self.assertFalse(sig.exists())
            # Az apps/ megváltozott, a dist nem lett újragenerálva.
            (self.repo.root / "apps" / "b-app.json").write_text(json.dumps(entry("b-app", "o/b")), encoding="utf-8")
            with self.assertRaises(sc.SigningError) as raised:
                sc.sign(self.repo.root, [("test-key", private)], OPENSSL)
            self.assertIn("apps/", str(raised.exception))
            self.repo.build()
            # Kézzel módosított (nem determinisztikus) dist.
            path = self.repo.root / "dist" / "v1" / "catalog.json"
            path.write_text(json.dumps(json.loads(path.read_text(encoding="utf-8"))), encoding="utf-8")
            with self.assertRaises(sc.SigningError):
                sc.sign(self.repo.root, [("test-key", private)], OPENSSL)
            self.assertFalse(sig.exists(), "érvénytelen dist nem kaphat aláírást")
            self.repo.build()
            sc.sign(self.repo.root, [("test-key", private)], OPENSSL)
            self.assertEqual(("valid", "test-key"), vc.verify_signature(self.repo.root, OPENSSL))

    @unittest.skipIf(OPENSSL is None, "nincs openssl")
    def test_replaced_dist_without_a_new_signature_fails_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            private = pathlib.Path(tmp) / "k.key"
            subprocess.run([OPENSSL, "ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", str(private)], check=True, capture_output=True)
            subprocess.run([OPENSSL, "pkey", "-in", str(private), "-pubout", "-out", str(self.repo.root / "keys" / "test-key.pub")], check=True, capture_output=True)
            sc.sign(self.repo.root, [("test-key", private)], OPENSSL)
            # Egy PR lecseréli a dist-et (szabályos alakban), a régi aláírás marad: érvénytelen.
            (self.repo.root / "apps" / "evil.json").write_text(json.dumps(entry("evil", "evil/app")), encoding="utf-8")
            self.repo.build()
            self.assertTrue(any("érvénytelen aláírás" in p for p in vc.validate(self.repo.root, require_signature=True, openssl=OPENSSL)[0]))
            # …vagy törli az aláírást: a kötelező aláírás hiánya hiba (a workflow PR-on is megköveteli).
            (self.repo.root / "dist" / "v1" / "catalog.json.sig").unlink()
            self.assertIn("dist: hiányzik a catalog.json.sig", vc.validate(self.repo.root, require_signature=True, openssl=OPENSSL)[0])


if __name__ == "__main__":
    unittest.main()
