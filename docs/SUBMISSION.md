<!-- SPDX-FileCopyrightText: 2026 RepoShelf contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Submission guide

## What can be submitted?

An open-source Android app that:

1. is in a **public GitHub repository**;
2. publishes an **installable APK** as a **GitHub Release** (source code alone is not enough; AAB files cannot be
   installed);
3. signs its released APKs with **the developer's own key**. Releases signed with a public test or debug key are not
   accepted, because anyone could sign a fake update with such a key;
4. uses an **OSI- or FSF-approved license**;
5. contains no known malicious behavior and requests no hidden permissions that its core function does not need.

**Being listed in the catalog is not a security certification.** Inclusion is a technical and formal review, not a full
security audit.

By submitting, you agree that your contribution to the catalog data is dedicated to the public domain under
[CC0 1.0](../LICENSES/CC0-1.0.txt).

## How?

1. Fork the repository and create a new file: `apps/<id>.json` (format: [SCHEMA.md](SCHEMA.md)).
2. Run locally: `python tools/validate_catalog.py` and the tests: `python -m unittest discover -s tools` (on Windows:
   `python -X utf8 -I …`).
3. Open a pull request using the template. In the description include:
   - the repository link, and whether you are the app's developer;
   - if you know them: the package name (`packageName`) and the SHA-256 fingerprint of the signing certificate
     (`signingCertSha256`), and where they come from (for example a value published by the developer).
4. Do **not** change `dist/`: maintainers generate and sign it.

## Automatic checks (GitHub Actions, on every pull request)

`.github/workflows/validate.yml` runs `tools/validate_catalog.py`. It checks:

- JSON syntax and schema, required fields, unknown fields;
- that `id` is unique and matches the file name;
- the repository path format (`owner/name`; a full URL is not accepted) and that the repository is not already listed
  under another ID;
- metadata contradictions: the same `packageName` or `repositoryId` in two entries, `minVersionCode` without a package
  name, duplicate signer fingerprints or keywords;
- the allowed form of `assetFilter` (a regular expression with bounded running time, see [SCHEMA.md](SCHEMA.md)),
  invisible or bidirectional characters in names and keywords, duplicate JSON keys;
- that `dist/v1/catalog.json` is valid, deterministic and **signed** (also on pull requests: a submission does not change
  `dist`, so the existing signature stays valid);
- the public keys in `keys/` (only proper P-256 keys), listing which keys are trusted and which one verified the
  signature.

The action is pinned to a commit SHA, the workflow has read-only permissions, uses no secrets, and runs on
`pull_request` (not `pull_request_target`).

**What a green check does NOT prove:** a pull request runs the validator and workflow of its own version. If a pull
request changes anything outside `apps/` (`tools/`, `schema/`, `keys/`, `dist/`, `.github/`, `categories.json`), the
automatic result alone means nothing – see the reviewer's duties.

## Human review

A passing automatic check is not enough. A maintainer (CODEOWNERS) checks by hand that:

1. the repository exists and is public, and `repositoryId` matches the ID reported by GitHub
   (`https://api.github.com/repos/<owner>/<repo>` → `id`);
2. recent releases contain an installable APK signed with the developer's own key (`apksigner verify --print-certs`); a
   submitted `signingCertSha256` matches it; a submitted `packageName` matches the APK's;
3. the license and the conditions above are met, and the name and keywords do not imitate another app (including
   look-alike spellings, for example Cyrillic letters);
4. **the pull request touches only `apps/`.** If it changes anything else:
   - `tools/`, `.github/`, `schema/`, `categories.json`: line-by-line review; a green validation is no evidence here,
     because the pull request ran its own validator;
   - `keys/`: a pull request adding or changing a public key is **never** merged (only maintainers decide which keys are
     trusted; the validation output lists the keys it trusts);
   - `dist/`: contributors may not change it; such a pull request is rejected (only maintainers build `dist` from `apps/`);
5. changing the `source` of an existing entry (another repository under the same `id`) needs a separate justification and
   review: clients do not apply an entry that now points elsewhere to an app they already follow, but new users would
   install from the new repository.

After approval a maintainer merges the pull request, then rebuilds and signs the catalog:

```bash
python tools/build_catalog.py --serial <a number higher than the current one>
```

```bash
python tools/sign_catalog.py --key <keyId>=<private key outside the repository>
```

```bash
python tools/validate_catalog.py --require-signature
```

When the real key is in place, a protected signing workflow will do these steps on `main` (see below).

## Repository settings at publication (owner's duties)

These are configured in GitHub's settings; the repository content cannot enforce them:

1. **Protect `main`** (branch protection or ruleset): merge only through pull requests; at least one approval; "Require
   review from Code Owners"; "Dismiss stale approvals"; the `Katalógus-validáció` (catalog validation) check required; no force pushes or branch
   deletion; rules apply to administrators too (with a single maintainer this also blocks their own pull requests: a
   second maintainer is needed, or the administrator exception must be a conscious, documented choice).
2. **Actions:** the default `GITHUB_TOKEN` is read-only; workflows from outside contributors run only after approval; only
   GitHub's own actions and explicitly listed actions pinned to full commit SHAs are allowed; pull requests from forks get
   no secrets and no write access.
3. **Account:** two-factor authentication (preferably a hardware key) on the owner account; secret scanning and push
   protection enabled.
4. **The repository and default branch names must not change:** clients have
   `…/reposhelf-catalog/main/dist/v1/catalog.json` compiled in.
5. **Signing workflow (the key is a GitHub Actions secret):** the key is an *environment secret* in a protected
   environment (required reviewer, `main` only); the workflow runs only on `workflow_dispatch` or a `push` to `main`, never
   on pull requests; the job itself builds `dist` from `apps/`, runs the full validation, signs, verifies, and commits only
   the two `dist` files; the key goes to a temporary file (`umask 077`) deleted by an `if: always()` step, without
   `set -x` or printing the secret; the serial is the previous one + 1; a `concurrency` group prevents parallel runs.
   *(This workflow does not exist yet; it is created together with the real key.)*
6. **Key backup and rotation:** keep an offline backup of the private key; rotation is described in the "Signature"
   section of [SCHEMA.md](SCHEMA.md).
7. **Before the first public release:** create the real key, replace the test key in `keys/` and in the app's key list,
   re-sign, and update the app's built-in catalog. (The app's release build intentionally fails with the test key.)

## What is not accepted?

- Descriptions, README excerpts or other text copied from third parties (the catalog data is CC0-1.0).
- Data taken from F-Droid or IzzyOnDroid metadata (those are AGPL-licensed).
- Names or keywords imitating another app.

## Removal

An entry can be removed if the repository disappears, releases no longer contain an APK, the signer changes without
confirmation from the developer, or a security problem comes up. To request a removal, open an issue (or, for a security
problem, use the repository's private vulnerability reporting).
