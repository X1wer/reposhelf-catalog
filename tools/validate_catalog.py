# SPDX-FileCopyrightText: 2026 RepoShelf contributors
# SPDX-License-Identifier: Apache-2.0
"""A katalógus automatikus validációja (CI, C. 3.3.). Használat a repó gyökeréből:

    python tools/validate_catalog.py                       # bejegyzések, ellentmondások, dist, aláírás (ha van)
    python tools/validate_catalog.py --require-signature   # a dist aláírása kötelező (main ág)

Ellenőrzi:
  * a bejegyzések JSON-szintaxisát és sémáját, a kötelező mezőket (build_catalog.validate_entry);
  * a duplikált azonosítókat és repókat, a fájlnév és az id egyezését, a repó-útvonal formátumát;
  * a metaadat-ellentmondásokat (ugyanaz a packageName vagy repositoryId két bejegyzésben,
    minVersionCode csomagnév nélkül, ismétlődő aláíró-ujjlenyomat vagy kulcsszó);
  * a dist/v1/catalog.json fejlécét és bejegyzéseit, determinisztikus formáját;
  * a dist/v1/catalog.json.sig aláírását a keys/*.pub nyilvános kulcsokkal (OpenSSL).

A repó elérhetőségét és a repositoryId-t a GitHub API-val NEM ellenőrzi (hálózatfüggetlen, determinisztikus CI);
ezt az emberi jóváhagyás része (docs/SUBMISSION.md). A katalógusban szereplés nem biztonsági tanúsítás.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build_catalog as bc  # noqa: E402

MAX_SIGNATURE_FILE = 16 * 1024


def contradictions(entries: list[dict]) -> list[str]:
    problems: list[str] = []
    by_package: dict[str, str] = {}
    by_repo_id: dict[int, str] = {}
    for e in entries:
        eid = e["id"]
        package = e.get("packageName")
        if package:
            if package in by_package:
                problems.append(f"{eid}: a packageName ({package}) már szerepel itt: {by_package[package]}")
            by_package.setdefault(package, eid)
        repo_id = e["source"].get("repositoryId")
        if repo_id is not None:
            if repo_id in by_repo_id:
                problems.append(f"{eid}: a repositoryId ({repo_id}) már szerepel itt: {by_repo_id[repo_id]}")
            by_repo_id.setdefault(repo_id, eid)
        if "minVersionCode" in e and not package:
            problems.append(f"{eid}: minVersionCode csak packageName mellett értelmes")
        certs = e.get("signingCertSha256", [])
        if len(set(certs)) != len(certs):
            problems.append(f"{eid}: ismétlődő signingCertSha256")
        keywords = [k.strip().lower() for k in e.get("keywords", [])]
        if len(set(keywords)) != len(keywords):
            problems.append(f"{eid}: ismétlődő kulcsszó")
    return problems


def _parse_time(value: object) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def validate_dist(root: pathlib.Path, categories: set[str]) -> tuple[list[str], list[dict]]:
    path = root / "dist" / "v1" / "catalog.json"
    if not path.is_file():
        return ["hiányzik a dist/v1/catalog.json"], []
    raw = path.read_bytes()
    try:
        catalog = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"dist: hibás JSON ({exc})"], []
    problems: list[str] = []
    if not isinstance(catalog, dict):
        return ["dist: a gyökér nem objektum"], []
    if catalog.get("schemaVersion") != bc.SCHEMA_VERSION:
        problems.append("dist: a schemaVersion 1 legyen")
    serial = catalog.get("catalogSerial")
    if not bc._is_int(serial) or serial < 1:
        problems.append("dist: a catalogSerial pozitív egész")
    generated, expires = _parse_time(catalog.get("generatedAt")), _parse_time(catalog.get("expiresAt"))
    if generated is None or expires is None:
        problems.append("dist: hibás generatedAt / expiresAt (YYYY-MM-DDTHH:MM:SSZ)")
    elif expires <= generated:
        problems.append("dist: az expiresAt a generatedAt után legyen")
    apps = catalog.get("apps")
    if not isinstance(apps, list):
        return problems + ["dist: hiányzó apps lista"], []
    ids: set[str] = set()
    for app in apps:
        app_id = app.get("id") if isinstance(app, dict) else None
        errors = bc.validate_entry(app, f"{app_id}.json", categories)
        problems.extend(f"dist/{app_id}: {e}" for e in errors)
        if app_id in ids:
            problems.append(f"dist/{app_id}: duplikált id")
        ids.add(app_id)
    if [a.get("id") for a in apps if isinstance(a, dict)] != sorted(ids - {None}):
        problems.append("dist: a bejegyzések nincsenek id szerint rendezve")
    if not problems and bc.serialize(catalog) != raw:
        problems.append("dist: nem a build_catalog.py determinisztikus kimenete (kézzel módosították?)")
    return problems, apps


def verify_signature(root: pathlib.Path, openssl: str = "openssl") -> tuple[str, str | None]:
    """('valid', keyId) / ('missing', None) / ('invalid', ok)."""
    catalog = root / "dist" / "v1" / "catalog.json"
    sig_path = catalog.with_name("catalog.json.sig")
    if not sig_path.is_file():
        return "missing", None
    if sig_path.stat().st_size > MAX_SIGNATURE_FILE:
        return "invalid", "túl nagy aláírásfájl"
    try:
        document = json.loads(sig_path.read_text(encoding="utf-8"))
        signatures = document["signatures"]
        if document.get("format") != 1 or not isinstance(signatures, list):
            return "invalid", "ismeretlen aláírásformátum"
    except (ValueError, KeyError, TypeError):
        return "invalid", "hibás aláírásfájl"
    keys = {p.name[: -len(".pub")]: p for p in sorted((root / "keys").glob("*.pub"))}
    with tempfile.TemporaryDirectory() as tmp:
        for i, sig in enumerate(signatures):
            if not isinstance(sig, dict) or sig.get("algorithm") != "ecdsa-p256-sha256":
                continue
            key = keys.get(sig.get("keyId"))
            if key is None:
                continue
            try:
                der = base64.b64decode(sig.get("value", ""), validate=True)
            except (ValueError, TypeError):
                continue
            der_path = pathlib.Path(tmp) / f"sig{i}.der"
            der_path.write_bytes(der)
            result = subprocess.run(
                [openssl, "dgst", "-sha256", "-verify", str(key), "-signature", str(der_path), str(catalog)],
                capture_output=True, check=False,
            )
            if result.returncode == 0:
                return "valid", sig["keyId"]
    return "invalid", "nincs érvényes aláírás ismert nyilvános kulccsal"


def validate(root: pathlib.Path, require_signature: bool, openssl: str = "openssl") -> tuple[list[str], list[str]]:
    """(hibák, megjegyzések)."""
    problems: list[str] = []
    notes: list[str] = []
    categories = set(json.loads((root / "categories.json").read_text(encoding="utf-8"))["categories"])
    try:
        entries = bc.load_entries(root)
    except bc.CatalogError as exc:
        problems.extend(str(exc).splitlines())
        entries = []
    problems.extend(contradictions(entries))
    dist_problems, dist_apps = validate_dist(root, categories)
    problems.extend(dist_problems)
    if entries and dist_apps and sorted(entries, key=lambda e: e["id"]) != dist_apps:
        notes.append("az apps/ és a dist/ eltér: a karbantartó a beolvasztás után újragenerálja és újra aláírja a dist-et")
    status, detail = verify_signature(root, openssl)
    if status == "valid":
        notes.append(f"aláírás rendben ({detail})")
    elif status == "invalid":
        problems.append(f"dist: érvénytelen aláírás: {detail}")
    elif require_signature:
        problems.append("dist: hiányzik a catalog.json.sig")
    else:
        notes.append("nincs aláírás (a main ágon kötelező)")
    return problems, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parent.parent)
    parser.add_argument("--require-signature", action="store_true")
    parser.add_argument("--openssl", default="openssl")
    args = parser.parse_args(argv)
    problems, notes = validate(args.root, args.require_signature, args.openssl)
    for note in notes:
        print(f"MEGJEGYZÉS: {note}")
    if problems:
        print("HIBA:\n" + "\n".join(problems), file=sys.stderr)
        return 1
    print("OK: a katalógus érvényes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
