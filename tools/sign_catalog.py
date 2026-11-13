# SPDX-FileCopyrightText: 2026 RepoShelf contributors
# SPDX-License-Identifier: Apache-2.0
"""A katalógus leválasztott aláírása (docs/SCHEMA.md „Aláírás”, az app docs/ARCHITECTURE.md 7.3. pontja).

Használat (a repó gyökeréből; a PRIVÁT kulcs a repón KÍVÜL van):

    python tools/sign_catalog.py --key catalog-2026-a=/biztonságos/hely/catalog-2026-a.key

Több kulcs (rotáció idején) több --key kapcsolóval adható meg. A kimenet: dist/v1/catalog.json.sig

Algoritmus: ECDSA P-256 / SHA-256 a dist/v1/catalog.json PONTOS bájtjain, DER-kódolt aláírással (base64).
Az aláírást az OpenSSL parancssori eszköze készíti; a Python standard könyvtárában nincs ECDSA.
"""

from __future__ import annotations

import argparse
import base64
import json
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build_catalog as bc  # noqa: E402
import validate_catalog as vc  # noqa: E402

ALGORITHM = "ecdsa-p256-sha256"
SIGNATURE_FORMAT = 1
KEY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")


class SigningError(Exception):
    pass


def _inside(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def sign_bytes(catalog: pathlib.Path, key: pathlib.Path, openssl: str = "openssl") -> bytes:
    """DER-kódolt ECDSA-aláírás a fájl pontos bájtjaira."""
    result = subprocess.run(
        [openssl, "dgst", "-sha256", "-sign", str(key), str(catalog)],
        capture_output=True, check=False,
    )
    if result.returncode != 0 or not result.stdout:
        raise SigningError(f"az aláírás nem sikerült ({key.name}): {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def public_key_der(key: pathlib.Path, openssl: str = "openssl") -> bytes:
    """A privát kulcshoz tartozó nyilvános kulcs (SubjectPublicKeyInfo, DER)."""
    result = subprocess.run([openssl, "pkey", "-in", str(key), "-pubout", "-outform", "DER"], capture_output=True, check=False)
    if result.returncode != 0 or not result.stdout:
        raise SigningError(f"a kulcs nem olvasható ({key.name})")
    return result.stdout


def check_dist(root: pathlib.Path) -> None:
    """Aláírás előtt: a dist érvényes, és pontosan az apps/ jelenlegi tartalmából készült.

    Az aláírás a kliensek számára hitelesíti a fájlt, ezért kézzel módosított, érvénytelen vagy az apps/-tól eltérő
    (pl. egy PR-ban becsempészett) dist soha nem kaphat aláírást.
    """
    try:
        entries = bc.load_entries(root)
    except bc.CatalogError as exc:
        raise SigningError(f"érvénytelen bejegyzés(ek):\n{exc}") from exc
    categories = set(json.loads((root / "categories.json").read_text(encoding="utf-8"))["categories"])
    problems, dist_apps = vc.validate_dist(root, categories)
    problems = problems + vc.contradictions(entries)
    if problems:
        raise SigningError("a dist nem írható alá:\n" + "\n".join(problems))
    if sorted(entries, key=lambda e: e["id"]) != dist_apps:
        raise SigningError("a dist nem az apps/ jelenlegi tartalmából készült (előbb: tools/build_catalog.py --serial N)")


def build_signature_file(signatures: list[tuple[str, bytes]]) -> bytes:
    document = {
        "format": SIGNATURE_FORMAT,
        "signatures": [
            {"keyId": key_id, "algorithm": ALGORITHM, "value": base64.b64encode(der).decode("ascii")}
            for key_id, der in signatures
        ],
    }
    return (json.dumps(document, indent=2) + "\n").encode("utf-8")


def sign(root: pathlib.Path, keys: list[tuple[str, pathlib.Path]], openssl: str = "openssl") -> pathlib.Path:
    catalog = root / "dist" / "v1" / "catalog.json"
    if not catalog.is_file():
        raise SigningError("hiányzik a dist/v1/catalog.json (előbb: tools/build_catalog.py)")
    if not keys:
        raise SigningError("legalább egy --key kell")
    signatures: list[tuple[str, bytes]] = []
    for key_id, key_path in keys:
        if not KEY_ID_RE.fullmatch(key_id):
            raise SigningError(f"érvénytelen kulcsazonosító: {key_id!r}")
        if _inside(key_path, root):
            raise SigningError(f"a privát kulcs nem lehet a repóban: {key_path}")
        if not key_path.is_file():
            raise SigningError(f"a kulcsfájl nem található: {key_path}")
        # A kulcsnak P-256-nak kell lennie, és a nyilvános részének egyeznie kell a repóban közzétett keys/<id>.pub-bal:
        # különben a kliensek (és a validátor) úgysem fogadnák el, vagy rossz kulcs kerülne használatba.
        published = vc.read_p256_public_key(root / "keys" / f"{key_id}.pub")
        if published is None:
            raise SigningError(f"hiányzik vagy nem P-256 nyilvános kulcs: keys/{key_id}.pub")
        if public_key_der(key_path, openssl) != published:
            raise SigningError(f"a megadott privát kulcs nem a keys/{key_id}.pub párja")
        signatures.append((key_id, sign_bytes(catalog, key_path, openssl)))
    check_dist(root)
    out = catalog.with_name("catalog.json.sig")
    out.write_bytes(build_signature_file(signatures))
    # Az elkészült aláírás visszaellenőrzése ugyanazzal a kóddal, amellyel a CI ellenőriz.
    status, detail = vc.verify_signature(root, openssl)
    if status != "valid":
        out.unlink()
        raise SigningError(f"az elkészült aláírás nem ellenőrizhető: {detail}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parent.parent)
    parser.add_argument("--key", action="append", default=[], metavar="KULCSAZONOSÍTÓ=ÚTVONAL")
    parser.add_argument("--openssl", default="openssl")
    args = parser.parse_args(argv)
    try:
        keys = []
        for spec in args.key:
            key_id, sep, path = spec.partition("=")
            if not sep:
                raise SigningError(f"a --key alakja: azonosító=útvonal ({spec!r})")
            keys.append((key_id, pathlib.Path(path)))
        out = sign(args.root, keys, args.openssl)
        print(f"Kész: {out.relative_to(args.root)} ({len(keys)} aláírás)")
        return 0
    except SigningError as exc:
        print(f"HIBA: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
