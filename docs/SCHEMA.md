<!-- SPDX-FileCopyrightText: 2026 RepoShelf contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Catalog schema – schemaVersion 1

The catalog is a public list of open-source Android apps published on GitHub. It contains **only the minimum data needed
for searching and identification**. Descriptions, READMEs, icons, screenshots and APK files are not part of it: the
RepoShelf app requests them directly from the listed repository.

**Being listed in the catalog is not a security certification.**

## Files

| File | Role |
|---|---|
| `apps/<id>.json` | One app's entry. Contributors edit these (one app per file → few merge conflicts). |
| `categories.json` | The fixed list of category IDs. |
| `schema/app-entry.v1.schema.json` | JSON Schema (draft 2020-12) of an entry – documentation; the Python validator is authoritative. |
| `schema/catalog.v1.schema.json` | JSON Schema of the built catalog – documentation. |
| `dist/v1/catalog.json` | The built catalog downloaded by the app. Generated; never edited by hand. |
| `dist/v1/catalog.json.sig` | Detached signature(s) of `catalog.json`. |
| `keys/<keyId>.pub` | Public keys of the catalog signing keys (PEM). Private keys are never in the repository. |
| `tools/` | `build_catalog.py` (validate and build), `validate_catalog.py` (CI validation), `sign_catalog.py` (signing), tests. |

## The built catalog (`dist/v1/catalog.json`)

```json
{
  "schemaVersion": 1,
  "catalogSerial": 1,
  "generatedAt": "2026-11-10T00:00:00Z",
  "expiresAt": "2027-02-08T00:00:00Z",
  "apps": [ { "...": "entries, sorted by id" } ]
}
```

| Field | Required | Meaning |
|---|---|---|
| `schemaVersion` | yes | Major schema version. A client only processes the major versions it knows (see below). |
| `catalogSerial` | yes | Monotonically increasing integer, at most 2^40. Clients reject a catalog with a lower serial than the one they accepted (rollback protection); an equal serial is only accepted with identical content. The serial can never go back, so `build_catalog.py` allows increasing it by at most 1000 at a time (against typos). |
| `generatedAt` | yes | Build time (ISO 8601, UTC). Clients reject a catalog generated more than 24 hours in the future. |
| `expiresAt` | yes | Until when the catalog counts as fresh: at most 366 days after `generatedAt` (90 days recommended). **Clients do not accept an already expired catalog from the network** (so a replayed old catalog cannot replace a newer one); they keep their existing catalog and warn that it may be out of date. Maintainers must therefore rebuild and re-sign the catalog before it expires. |
| `apps` | yes | The entries (1–20,000). Clients do not accept an empty catalog. |

The build is deterministic: UTF-8, LF line endings, entries sorted by `id`.

## An entry (`apps/<id>.json`)

```json
{
  "id": "obtainium",
  "name": "Obtainium",
  "source": { "provider": "github", "repository": "ImranR98/Obtainium", "repositoryId": 523534328 },
  "keywords": ["updates", "app manager", "frissítés"],
  "category": "system",
  "assetFilter": "^(?!.*fdroid).*\\.apk$"
}
```

| Field | Required | Rule | Purpose |
|---|---|---|---|
| `id` | yes | `^[a-z0-9][a-z0-9._-]{1,63}$`, unique, equal to the file name, not a Windows reserved name | Stable catalog ID. Cannot change after publication. |
| `name` | yes | 1–100 characters (UTF-16 units); no control, invisible or bidirectional-override characters | Displayed name, search. |
| `source.provider` | yes | currently only `github` | Source provider. Clients skip entries with an unknown provider (forward compatibility). |
| `source.repository` | yes | `owner/name` following GitHub naming rules (not a full URL) | The repository path. |
| `source.repositoryId` | recommended | positive integer | GitHub's permanent repository ID. If a repository with a different ID appears under the name (the original was deleted and someone recreated it), clients refuse to update from it (protection against repository hijacking). |
| `packageName` | no | Android package name | The expected package name; clients do not install a different one. |
| `signingCertSha256` | no | up to 10 lower-case, 64-digit hex values | Expected signing certificate fingerprint(s). Stronger than the signer recorded on first installation ("trust on first use"); checked independently of it. |
| `minVersionCode` | no | ≥ 0; requires `packageName` | Clients do not install an older version. |
| `keywords` | no | up to 30, each 1–40 characters; no invisible characters; no duplicates | Search keywords – English and Hungarian are welcome. Clients search ignoring accents and case. |
| `category` | yes | one of `categories.json` | Category. Clients treat an unknown category as `other`. |
| `assetFilter` | no | a **restricted** regular expression of at most 200 characters (see below) | When a release contains several variants (for example an F-Droid and a GitHub build), selects the installable file. |

Category IDs: `communication`, `development`, `education`, `games`, `graphics`, `internet`, `maps`, `multimedia`,
`productivity`, `reading`, `science`, `security`, `system`, `utilities`, `other`.

### Allowed form of `assetFilter`

The filter runs on the device, against file names chosen by the repository owner. An arbitrary regular expression could
stall the client with a crafted file name (ReDoS), so only patterns with a predictably bounded running time are
accepted. The client (`AssetFilterSyntax`) and the validator apply the same rule:

- printable ASCII only;
- allowed: literals, `.`, character classes (`[a-z0-9.]`, not nested), `\d` `\w` `\s`, escaped punctuation (`\.`), `^`
  `$`, alternation (`a|b`), groups (`(...)`, `(?:...)`), lookahead (`(?=...)`, `(?!...)`);
- repetition (`*`, `+`, `?`) **only on a single character or character class**, never on a group; no lazy (`*?`),
  possessive (`*+`) or counted (`{2,5}`) repetition, backreferences, lookbehind, named groups or flags (`(?i)`);
- cost limit: 8 points for every `*` and `+`, 1 point for every `?` and `|`, 8 more points if the pattern does not start
  with `^` (or has a top-level `|`); the total must be at most 22. In practice: at most two `*` / `+` in a pattern anchored
  with `^`.

| Good | Rejected | Instead |
|---|---|---|
| `^app-[0-9.]+-release\.apk$` | `^app-\d+\.\d+\.\d+-release\.apk$` (three `+`) | one character class: `[0-9.]+` |
| `^(?!.*fdroid).*\.apk$` | `^(app-?)+release\.apk$` (repeated group) | `^app-?release\.apk$` |
| `^app-(arm64-v8a\|universal)-release\.apk$` | `^app(?:-foss)?\.apk$` (optional group) | `^(?:app\|app-foss)\.apk$` |

The filter does not have to select by ABI: the client picks the file for the device's processor itself.

The catalog must **not** contain descriptions, README excerpts or other text copied from third parties – because the
catalog data is CC0-1.0, and because of the minimum-data principle. F-Droid and IzzyOnDroid metadata are AGPL-licensed
and must not be copied.

## Compatibility and versioning

- **Backward-compatible extension** (a new optional field): `schemaVersion` stays the same; older clients ignore unknown
  fields.
- **Incompatible change:** a new major version (`schemaVersion: 2`) on a **new path** (`dist/v2/catalog.json`). During
  the transition `dist/v1/` keeps being updated, so older clients keep working.
- A client that receives a newer `schemaVersion` than it supports does not process it: it keeps its last valid catalog and
  tells the user to update the app.
- Clients skip invalid entries one by one. If more than 20% of the entries are invalid, the whole catalog is rejected and
  the previous one stays in use. Entries with an unknown provider are not invalid: they are skipped and not counted.
- **The validator must never be more permissive than the client.** Anything the client would reject must also be rejected
  by the tools here; both rule sets change together (the app's `BundledCatalogTest` checks that the published catalog is
  fully accepted by the client).

## Signature

Next to `dist/v1/catalog.json` there is a detached signature, `dist/v1/catalog.json.sig`. It covers the **exact bytes**
of the catalog file (`.gitattributes` fixes LF line endings; the `.sig` file is treated as binary).

```json
{"format": 1, "signatures": [{"keyId": "catalog-2026-a", "algorithm": "ecdsa-p256-sha256", "value": "<base64 DER>"}]}
```

- Algorithm: ECDSA P-256 / SHA-256, DER-encoded signature, base64. Clients skip signatures with an unknown `algorithm`.
- Several signatures are allowed (key rotation; clients read at most 8, and the file may be at most 16 KiB). A client
  accepts the catalog if at least one signature made with a public key compiled into the app (`keyId` → key) is valid.
  If the signature is missing or invalid, the previous valid catalog stays in use.
- Public keys: `keys/<keyId>.pub` (PEM, SubjectPublicKeyInfo; P-256 / secp256r1 only). The private key never enters the
  repository.
- Signing: `python tools/sign_catalog.py --key <keyId>=<path to the private key outside the repository>`; checking:
  `python tools/validate_catalog.py --require-signature`. The signing tool only signs a valid `dist` built from the current
  `apps/`, only with a key whose public part is `keys/<keyId>.pub`, and verifies the result.
- **Key change and revocation:** clients remember which key accepted their stored catalog. If, after an app update, that
  key is no longer trusted, they drop the stored catalog and start again from the built-in one. During a key change the
  catalog must therefore be signed with both keys, and the old key may only be removed from the app after a release that
  knows the new key is widespread.
- **Currently a test key** (`catalog-test-2026a`) signs the catalog. The real key will be created when the repository is
  published and kept as a GitHub Actions secret in a protected environment, with an offline backup.
