<!-- SPDX-FileCopyrightText: 2026 RepoShelf contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# RepoShelf catalog

A small, signed, searchable catalog of open-source Android apps published on GitHub, used by the
[RepoShelf](https://github.com/X1wer/reposhelf) app manager. Each entry contains only an app's name, its GitHub
repository, keywords, a category and – optionally – data that helps verify it (permanent repository ID, package name,
signing certificate fingerprints, minimum version code, an asset filter). Everything else – description, README, icon,
releases and APK files – RepoShelf requests directly from the app's own repository. **This repository stores no APK
files.**

*Magyarul:* a RepoShelf alkalmazáskezelő aláírt, kereshető katalógusa GitHubon közzétett, nyílt forráskódú
Android-alkalmazásokról. Egy bejegyzés csak a nevet, a GitHub-repót, kulcsszavakat, kategóriát és opcionális ellenőrző
adatokat tartalmaz; APK-fájlt a repó nem tárol.

> **Status: not yet published.** The catalog is currently signed with a **test key** (`keys/catalog-test-2026a.pub`).
> The real signing key will be created when the repository is published; until then RepoShelf release builds cannot be
> made.

**Being listed in the catalog is not a security certification.** Inclusion is a technical and formal review, not a
security audit. The apps are made by independent developers.

## Contents

| Path | Contents |
|---|---|
| `apps/<id>.json` | one file per app – this is what contributors edit |
| `categories.json` | the fixed category IDs |
| `dist/v1/catalog.json`, `dist/v1/catalog.json.sig` | the built catalog and its detached ECDSA P-256 signature – what the app downloads |
| `keys/` | public keys of the catalog signing keys |
| `schema/` | JSON Schema descriptions (documentation) |
| `tools/` | build, validation and signing tools (Python 3, standard library only) and their tests |
| `docs/SCHEMA.md` | the catalog format, compatibility rules and signature |
| `docs/SUBMISSION.md` | how to submit an app, automatic checks, human review, repository settings |

## Submitting an app

Read [docs/SUBMISSION.md](docs/SUBMISSION.md), add `apps/<id>.json` in a pull request, and run the validation locally:

```bash
python tools/validate_catalog.py
```

```bash
python -m unittest discover -s tools
```

On Windows use `python -X utf8 -I …`. Do not change `dist/`: maintainers build and sign it.

## Maintainer commands

```bash
python tools/build_catalog.py --serial <previous serial + 1>
```

```bash
python tools/sign_catalog.py --key <keyId>=<path to the private key outside the repository>
```

```bash
python tools/validate_catalog.py --require-signature
```

The serial may grow by at most 1000 at a time; the catalog must be re-signed before `expiresAt` (90 days recommended), or
clients stop accepting updates and warn that the catalog may be out of date. After rebuilding, the RepoShelf app's
built-in copy (`assets/catalog/catalog-v1.json` and `.sig`) must be updated with the identical files.

## License

| What | License |
|---|---|
| Catalog data: `apps/`, `categories.json`, `dist/`, `schema/`, `keys/` | [CC0 1.0](LICENSES/CC0-1.0.txt) – public domain dedication |
| Tools and CI: `tools/`, `.github/` | [Apache License 2.0](LICENSES/Apache-2.0.txt) |
| Documentation: `README.md`, `docs/` | [CC BY 4.0](LICENSES/CC-BY-4.0.txt) |

See [LICENSE](LICENSE). Contributions to the catalog data are accepted under CC0 1.0. Names of apps are used only to
identify them and belong to their owners. "GitHub" is a trademark of GitHub, Inc.; this project is not affiliated with
GitHub.

Security problems with a catalog entry or the tools: please report them privately through the repository's "Report a
vulnerability" feature (enabled when the repository is published).
