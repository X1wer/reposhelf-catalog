<!-- SPDX-License-Identifier: CC0-1.0 -->
## Add or change an app

- **Repository:** https://github.com/<owner>/<repo>
- **I am the developer:** yes / no (if no: how do you know the developer agrees?)
- **Package name (`packageName`), if known:**
- **Signing certificate SHA-256 (`signingCertSha256`), if known, and its source:**

### Checklist

- [ ] I changed only `apps/<id>.json` (maintainers generate and sign `dist/`).
- [ ] `python tools/validate_catalog.py` passes locally.
- [ ] The repository is public and its GitHub Releases contain an installable APK (not only an AAB).
- [ ] The released APKs are signed with the developer's own key (not a public test or debug key).
- [ ] The license is OSI- or FSF-approved.
- [ ] I did not copy descriptions from third parties and did not use F-Droid or IzzyOnDroid metadata.
- [ ] I agree that my contribution to the catalog data is released under CC0 1.0.

> Being listed in the catalog is not a security certification. Inclusion needs a maintainer's approval.
> See [docs/SUBMISSION.md](../docs/SUBMISSION.md).
