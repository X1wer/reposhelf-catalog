# SPDX-FileCopyrightText: 2026 RepoShelf contributors
# SPDX-License-Identifier: Apache-2.0
"""A katalógus összeállítása az `apps/*.json` bejegyzésekből a `dist/v1/catalog.json` fájlba.

Használat (a repó gyökeréből):

    python tools/build_catalog.py --serial 2
    python tools/build_catalog.py --check      # csak ellenőrzés: érvényesek-e a bejegyzések

A szkript csak a Python standard könyvtárát használja. A CI-validáció a validate_catalog.py-ban, az aláírás a
sign_catalog.py-ban van (docs/SUBMISSION.md).

Szabályok (a kliens CatalogParser-ével összhangban, lásd docs/SCHEMA.md):
  * a fájlnév = az `id` + `.json`, az `id` egyedi és érvényes;
  * a repó (`owner/name`, kis- és nagybetűtől függetlenül) egyedi;
  * a kategória a `categories.json` listájából való;
  * a sorszám (`catalogSerial`) csak nőhet.

A validátor SOHA nem lehet megengedőbb a kliensnél: amit a kliens elutasítana, azt itt is el kell utasítani, különben
a CI zöld, miközben a kliensek kihagyják a bejegyzést (20% fölötti hibaaránynál az egész katalógust).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
import unicodedata

SCHEMA_VERSION = 1
DEFAULT_VALIDITY_DAYS = 90
# A kliens legfeljebb 400 napos érvényességet fogad el; itt szigorúbbak vagyunk.
MAX_VALIDITY_DAYS = 366
# A kliens felső korlátja a sorszámra; egy elírt, óriási sorszám minden későbbi katalógust kizárna.
MAX_SERIAL = 1 << 40
MAX_SERIAL_STEP = 1000
MAX_INT64 = (1 << 63) - 1

ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{1,63}")
OWNER_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
REPO_RE = re.compile(r"[A-Za-z0-9._-]{1,100}")
PACKAGE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
ALLOWED_KEYS = {"id", "name", "source", "packageName", "signingCertSha256", "minVersionCode", "keywords", "category", "assetFilter"}
ALLOWED_SOURCE_KEYS = {"provider", "repository", "repositoryId"}
PROVIDERS = {"github"}
# Windows alatt fenntartott eszköznevek: ilyen nevű fájl ott nem hozható létre és nem vehető ki a repóból.
RESERVED_NAMES = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
# Megjelenített szövegben (név, kulcsszó) tiltott Unicode-kategóriák: vezérlő, formázó (irányváltó, nulla szélességű),
# surrogate, magáncélú, ki nem osztott, sor- és bekezdéselválasztó. A kliens (DisplayText) ugyanezt utasítja el.
FORBIDDEN_CATEGORIES = {"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"}

ASSET_FILTER_MAX_LENGTH = 200
ASSET_FILTER_MAX_COST = 22


class CatalogError(Exception):
    pass


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def utf16_length(text: str) -> int:
    """A szöveg hossza UTF-16 kódegységben (a kliens így számolja a hosszkorlátokat)."""
    return sum(2 if ord(c) > 0xFFFF else 1 for c in text)


def is_display_safe(text: str) -> bool:
    """Megjeleníthető szöveg: nincs benne láthatatlan vagy a megjelenítést átrendező karakter (névhamisítás ellen)."""
    return all(unicodedata.category(c) not in FORBIDDEN_CATEGORIES for c in text)


def asset_filter_violation(pattern: str) -> str | None:
    """Az `assetFilter` hibája, vagy `None`, ha megengedett.

    Ugyanaz a szabály, mint a kliensben (`AssetFilterSyntax`): a szűrő az eszközön a repó tulajdonosa által megadott
    állományneveken fut, ezért csak olyan reguláris kifejezés fogadható el, amelynek a futási ideje kiszámíthatóan
    korlátos (ReDoS ellen). Megengedett: literálok, `.`, karakterosztály, `\\d` `\\w` `\\s`, kiléptetett írásjel, `^` `$`,
    `|`, csoport és előretekintés; ismétlés (`*` `+` `?`) csak egyetlen karakterre vagy karakterosztályra. Költség:
    8 pont minden `*` / `+`, 1 pont minden `?` és `|`, 8 pont, ha a minta nincs `^` jellel rögzítve; legfeljebb 22.
    """
    if not pattern or len(pattern) > ASSET_FILTER_MAX_LENGTH:
        return f"a hossz 1 és {ASSET_FILTER_MAX_LENGTH} karakter között lehet"
    if any(not " " <= c <= "~" for c in pattern):
        return "csak nyomtatható ASCII karakter megengedett"
    n = len(pattern)
    i = depth = stars = choices = 0
    top_level_alternation = False
    quantifiable = False  # az előző elem egyetlen karakter vagy karakterosztály volt-e

    def at(index: int) -> str | None:
        return pattern[index] if index < n else None

    def escape_violation(following: str | None) -> str | None:
        if following is None:
            return "csonka kiléptetés"
        if following.isalnum() and following not in "dws":
            return f"nem támogatott kiléptetés: \\{following}"
        return None

    while i < n:
        c = pattern[i]
        if c == "\\":
            problem = escape_violation(at(i + 1))
            if problem:
                return problem
            i += 2
            quantifiable = True
        elif c == "[":
            j = i + 1
            if at(j) == "^":
                j += 1
            if at(j) == "]":
                j += 1
            while j < n and pattern[j] != "]":
                if pattern[j] == "\\":
                    problem = escape_violation(at(j + 1))
                    if problem:
                        return problem
                    j += 2
                elif pattern[j] == "[":
                    return "beágyazott karakterosztály nem megengedett"
                elif pattern[j] == "&" and at(j + 1) == "&":
                    return "karakterosztály-metszet nem megengedett"
                else:
                    j += 1
            if j >= n:
                return "lezáratlan karakterosztály"
            i = j + 1
            quantifiable = True
        elif c == "(":
            if at(i + 1) == "?":
                if at(i + 2) not in (":", "=", "!"):
                    return "csak (?:…), (?=…) és (?!…) csoport megengedett"
                i += 3
            else:
                i += 1
            depth += 1
            quantifiable = False
        elif c == ")":
            depth -= 1
            if depth < 0:
                return "párosítatlan zárójel"
            i += 1
            quantifiable = False
        elif c == "|":
            choices += 1
            if depth == 0:
                top_level_alternation = True
            i += 1
            quantifiable = False
        elif c in "*+?":
            if not quantifiable:
                return "ismétlés csak egyetlen karakterre vagy karakterosztályra alkalmazható"
            if c == "?":
                choices += 1
            else:
                stars += 1
            if at(i + 1) in ("?", "+", "*", "{"):
                return "lusta, birtokos vagy halmozott ismétlés nem megengedett"
            i += 1
            quantifiable = False
        elif c in "{}":
            return "számlált ismétlés nem megengedett"
        elif c in "^$":
            i += 1
            quantifiable = False
        else:
            i += 1
            quantifiable = True
    if depth != 0:
        return "lezáratlan csoport"
    anchored = pattern.startswith("^") and not top_level_alternation
    cost = 8 * stars + choices + (0 if anchored else 8)
    if cost > ASSET_FILTER_MAX_COST:
        return "túl sok ismétlés vagy választás: a futási idő nem korlátozható (rögzítsd a mintát ^ jellel, vagy egyszerűsítsd)"
    return None


def validate_entry(entry: object, filename: str, categories: set[str]) -> list[str]:
    """A bejegyzés hibáinak listája (üres lista = érvényes)."""
    errors: list[str] = []
    if not isinstance(entry, dict):
        return ["a bejegyzés nem JSON-objektum"]
    unknown = set(entry) - ALLOWED_KEYS
    if unknown:
        errors.append(f"ismeretlen mező(k): {', '.join(sorted(unknown))}")

    entry_id = entry.get("id")
    if not isinstance(entry_id, str) or not ID_RE.fullmatch(entry_id):
        errors.append("érvénytelen vagy hiányzó id (kisbetű, szám, . _ -; 2–64 karakter)")
    elif entry_id.split(".")[0] in RESERVED_NAMES:
        errors.append(f"az id ({entry_id}) Windows alatt fenntartott fájlnév")
    elif filename != f"{entry_id}.json":
        errors.append(f"a fájlnév ({filename}) nem egyezik az id-vel ({entry_id}.json)")

    name = entry.get("name")
    if not isinstance(name, str) or not name.strip() or utf16_length(name.strip()) > 100 or not is_display_safe(name):
        errors.append("érvénytelen vagy hiányzó name (1–100 karakter, láthatatlan vagy vezérlőkarakter nélkül)")

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
        if (len(parts) != 2 or not OWNER_RE.fullmatch(parts[0]) or not REPO_RE.fullmatch(parts[1])
                or parts[1] in (".", "..") or parts[1].lower().endswith(".git")):
            errors.append("érvénytelen source.repository (owner/name)")
        if "repositoryId" in source and (not _is_int(source["repositoryId"]) or not 0 < source["repositoryId"] <= MAX_INT64):
            errors.append("a source.repositoryId pozitív (64 bites) egész szám")

    if "packageName" in entry:
        package = entry["packageName"]
        if not isinstance(package, str) or len(package) > 255 or not PACKAGE_RE.fullmatch(package):
            errors.append("érvénytelen packageName")

    certs = entry.get("signingCertSha256", [])
    if not isinstance(certs, list) or len(certs) > 10 or any(not isinstance(c, str) or not SHA256_RE.fullmatch(c) for c in certs):
        errors.append("a signingCertSha256 legfeljebb 10 darab kisbetűs, 64 jegyű hex érték")

    if "minVersionCode" in entry and (not _is_int(entry["minVersionCode"]) or not 0 <= entry["minVersionCode"] <= MAX_INT64):
        errors.append("a minVersionCode nemnegatív (64 bites) egész szám")

    keywords = entry.get("keywords", [])
    if (not isinstance(keywords, list) or len(keywords) > 30
            or any(not isinstance(k, str) or not k.strip() or utf16_length(k.strip()) > 40 or not is_display_safe(k) for k in keywords)):
        errors.append("a keywords legfeljebb 30 darab, egyenként 1–40 karakteres szöveg (láthatatlan karakter nélkül)")

    if entry.get("category") not in categories:
        errors.append(f"ismeretlen category: {entry.get('category')!r}")

    if "assetFilter" in entry:
        asset_filter = entry["assetFilter"]
        if not isinstance(asset_filter, str):
            errors.append("az assetFilter szöveg")
        else:
            problem = asset_filter_violation(asset_filter)
            if problem:
                errors.append(f"nem megengedett assetFilter: {problem} (docs/SCHEMA.md)")
            else:
                try:
                    re.compile(asset_filter)
                except re.error as exc:
                    errors.append(f"érvénytelen assetFilter: {exc}")
    return errors


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    """JSON-objektum ismétlődő kulcs nélkül (a jóváhagyó ne lásson mást, mint amit az eszköz használ)."""
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("ismétlődő kulcs a JSON-objektumban")
    return dict(pairs)


def load_entries(root: pathlib.Path) -> list[dict]:
    categories = set(json.loads((root / "categories.json").read_text(encoding="utf-8"))["categories"])
    entries: list[dict] = []
    problems: list[str] = []
    seen_ids: set[str] = set()
    seen_repos: dict[str, str] = {}
    for path in sorted((root / "apps").glob("*.json")):
        if path.is_symlink() or not path.is_file():
            problems.append(f"{path.name}: csak szabályos fájl lehet (szimbolikus link nem)")
            continue
        try:
            entry = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys)
        except (ValueError, UnicodeDecodeError) as exc:
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
    if not 1 <= serial <= MAX_SERIAL:
        raise CatalogError(f"a catalogSerial 1 és {MAX_SERIAL} között lehet")
    if not 1 <= validity_days <= MAX_VALIDITY_DAYS:
        raise CatalogError(f"az érvényesség 1 és {MAX_VALIDITY_DAYS} nap között lehet")
    if not entries:
        raise CatalogError("üres katalógus nem készíthető (a kliensek elutasítanák)")
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
            # Elírás ellen: a kliensek a nagyobb sorszámot véglegesen megjegyzik, visszalépni nem lehet.
            if args.serial > previous + MAX_SERIAL_STEP:
                raise CatalogError(f"a sorszám egyszerre legfeljebb {MAX_SERIAL_STEP}-rel nőhet (jelenlegi: {previous}, kért: {args.serial})")
        if args.generated_at:
            generated = dt.datetime.strptime(args.generated_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        else:
            generated = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        data = serialize(build(entries, args.serial, generated, args.validity_days))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        print(f"Kész: {out.relative_to(args.root)} ({len(entries)} bejegyzés, catalogSerial={args.serial})")
        return 0
    except (CatalogError, UnicodeEncodeError) as exc:
        print(f"HIBA:\n{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
