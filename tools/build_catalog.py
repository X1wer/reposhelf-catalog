# SPDX-FileCopyrightText: 2026 RepoShelf contributors
# SPDX-License-Identifier: Apache-2.0
"""A katalógus összeállítása az `apps/*.json` bejegyzésekből a `dist/v1/catalog.json` fájlba.

Használat (a repó gyökeréből):

    python tools/build_catalog.py --serial 2
    python tools/build_catalog.py --check      # csak ellenőrzés: érvényesek-e a bejegyzések

A szkript csak a Python standard könyvtárát használja. A teljes JSON Schema-validáció, a GitHub API-alapú
ellenőrzések és az aláírás a 7. munkamenetben kerülnek a CI-ba (docs/SUBMISSION.md).

Szabályok (a kliens CatalogParser-ével összhangban, lásd docs/SCHEMA.md):
  * a fájlnév = az `id` + `.json`, az `id` egyedi és érvényes;
  * a repó (`owner/name`, kis- és nagybetűtől függetlenül) egyedi;
  * a kategória a `categories.json` listájából való;
  * a sorszám (`catalogSerial`) csak nőhet.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys

SCHEMA_VERSION = 1
DEFAULT_VALIDITY_DAYS = 90

ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_KEYS = {"id", "name", "source", "packageName", "signingCertSha256", "minVersionCode", "keywords", "category", "assetFilter"}
ALLOWED_SOURCE_KEYS = {"provider", "repository", "repositoryId"}
PROVIDERS = {"github"}


class CatalogError(Exception):
    pass


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_entry(entry: object, filename: str, categories: set[str]) -> list[str]:
    """A bejegyzés hibáinak listája (üres lista = érvényes)."""
    errors: list[str] = []
    if not isinstance(entry, dict):
        return ["a bejegyzés nem JSON-objektum"]
    unknown = set(entry) - ALLOWED_KEYS
    if unknown:
        errors.append(f"ismeretlen mező(k): {', '.join(sorted(unknown))}")

    entry_id = entry.get("id")
    if not isinstance(entry_id, str) or not ID_RE.match(entry_id):
        errors.append("érvénytelen vagy hiányzó id (kisbetű, szám, . _ -; 2–64 karakter)")
    elif filename != f"{entry_id}.json":
        errors.append(f"a fájlnév ({filename}) nem egyezik az id-vel ({entry_id}.json)")

    name = entry.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100 or any(ord(c) < 32 for c in name):
        errors.append("érvénytelen vagy hiányzó name (1–100 karakter)")

    source = entry.get("source")
    if not isinstance(source, dict):
        errors.append("hiányzó source objektum")
    else:
        unknown_source = set(source) - ALLOWED_SOURCE_KEYS
        if unknown_source:
            errors.append(f"ismeretlen source-mező(k): {', '.join(sorted(unknown_source))}")
        if source.get("provider") not in PROVIDERS:
            errors.append("a source.provider jelenleg csak 'github' lehet")
        repository = source.get("repository")
        parts = repository.split("/") if isinstance(repository, str) else []
        if (len(parts) != 2 or not OWNER_RE.match(parts[0]) or not REPO_RE.match(parts[1])
                or parts[1] in (".", "..") or parts[1].lower().endswith(".git")):
            errors.append("érvénytelen source.repository (owner/name)")
        if "repositoryId" in source and (not _is_int(source["repositoryId"]) or source["repositoryId"] <= 0):
            errors.append("a source.repositoryId pozitív egész szám")

    if "packageName" in entry:
        package = entry["packageName"]
        if not isinstance(package, str) or len(package) > 255 or not PACKAGE_RE.match(package):
            errors.append("érvénytelen packageName")

    certs = entry.get("signingCertSha256", [])
    if not isinstance(certs, list) or len(certs) > 10 or any(not isinstance(c, str) or not SHA256_RE.match(c) for c in certs):
        errors.append("a signingCertSha256 legfeljebb 10 darab kisbetűs, 64 jegyű hex érték")

    if "minVersionCode" in entry and (not _is_int(entry["minVersionCode"]) or entry["minVersionCode"] < 0):
        errors.append("a minVersionCode nemnegatív egész szám")

    keywords = entry.get("keywords", [])
    if (not isinstance(keywords, list) or len(keywords) > 30
            or any(not isinstance(k, str) or not k.strip() or len(k.strip()) > 40 for k in keywords)):
        errors.append("a keywords legfeljebb 30 darab, egyenként 1–40 karakteres szöveg")

    if entry.get("category") not in categories:
        errors.append(f"ismeretlen category: {entry.get('category')!r}")

    if "assetFilter" in entry:
        asset_filter = entry["assetFilter"]
        if not isinstance(asset_filter, str) or len(asset_filter) > 200:
            errors.append("az assetFilter legfeljebb 200 karakteres szöveg")
        else:
            try:
                re.compile(asset_filter)
            except re.error as exc:
                errors.append(f"érvénytelen assetFilter: {exc}")
    return errors


def load_entries(root: pathlib.Path) -> list[dict]:
    categories = set(json.loads((root / "categories.json").read_text(encoding="utf-8"))["categories"])
    entries: list[dict] = []
    problems: list[str] = []
    seen_ids: set[str] = set()
    seen_repos: dict[str, str] = {}
    for path in sorted((root / "apps").glob("*.json")):
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            problems.append(f"{path.name}: hibás JSON ({exc})")
            continue
        errors = validate_entry(entry, path.name, categories)
        if not errors:
            repo_key = entry["source"]["repository"].lower()
            if entry["id"] in seen_ids:
                errors.append("duplikált id")
            if repo_key in seen_repos:
                errors.append(f"a repó már szerepel: {seen_repos[repo_key]}")
        if errors:
            problems.extend(f"{path.name}: {e}" for e in errors)
            continue
        seen_ids.add(entry["id"])
        seen_repos[entry["source"]["repository"].lower()] = path.name
        entries.append(entry)
    if problems:
        raise CatalogError("\n".join(problems))
    return entries


def build(entries: list[dict], serial: int, generated_at: dt.datetime, validity_days: int) -> dict:
    if serial < 1:
        raise CatalogError("a catalogSerial legalább 1")
    expires_at = generated_at + dt.timedelta(days=validity_days)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return {
        "schemaVersion": SCHEMA_VERSION,
        "catalogSerial": serial,
        "generatedAt": generated_at.strftime(fmt),
        "expiresAt": expires_at.strftime(fmt),
        "apps": sorted(entries, key=lambda e: e["id"]),
    }


def serialize(catalog: dict) -> bytes:
    # Determinisztikus kimenet: UTF-8, LF sorvég, záró újsor (az aláírás a pontos bájtokra vonatkozik).
    return (json.dumps(catalog, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parent.parent)
    parser.add_argument("--serial", type=int, help="az új catalogSerial (nagyobb kell legyen a meglévőnél)")
    parser.add_argument("--generated-at", help="ISO-8601 UTC időpont (alapértelmezés: most)")
    parser.add_argument("--validity-days", type=int, default=DEFAULT_VALIDITY_DAYS)
    parser.add_argument("--check", action="store_true", help="csak a bejegyzések ellenőrzése, írás nélkül")
    args = parser.parse_args(argv)

    try:
        entries = load_entries(args.root)
        if args.check:
            print(f"OK: {len(entries)} érvényes bejegyzés")
            return 0
        if args.serial is None:
            raise CatalogError("a --serial megadása kötelező")
        out = args.root / "dist" / "v1" / "catalog.json"
        if out.exists():
            previous = json.loads(out.read_text(encoding="utf-8")).get("catalogSerial", 0)
            if args.serial <= previous:
                raise CatalogError(f"a sorszám csak nőhet (jelenlegi: {previous}, kért: {args.serial})")
        if args.generated_at:
            generated = dt.datetime.strptime(args.generated_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        else:
            generated = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        data = serialize(build(entries, args.serial, generated, args.validity_days))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        print(f"Kész: {out.relative_to(args.root)} ({len(entries)} bejegyzés, catalogSerial={args.serial})")
        return 0
    except CatalogError as exc:
        print(f"HIBA:\n{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
