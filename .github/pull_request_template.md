<!-- SPDX-License-Identifier: CC0-1.0 -->
## Alkalmazás felvétele / módosítása

- **Repó:** https://github.com/<owner>/<repo>
- **A fejlesztő vagyok:** igen / nem (ha nem: honnan tudod, hogy a fejlesztő egyetért?)
- **Csomagazonosító (`packageName`), ha ismert:**
- **Aláíró tanúsítvány SHA-256 (`signingCertSha256`), ha ismert, és a forrása:**

### Ellenőrzőlista

- [ ] Csak az `apps/<id>.json` fájlt módosítottam (a `dist/` könyvtárat a karbantartók generálják és írják alá).
- [ ] `python tools/validate_catalog.py` helyben hibátlan.
- [ ] A repó nyilvános, és a GitHub Releases alatt telepíthető APK van (nem csak AAB).
- [ ] A kiadott APK-kat a fejlesztő saját kulcsa írja alá (nem nyilvános teszt- vagy debug-kulcs).
- [ ] A licenc OSI- vagy FSF-elfogadott.
- [ ] Nem másoltam be harmadik féltől származó leírást, és nem F-Droid/IzzyOnDroid-metaadatból dolgoztam.

> A katalógusban szereplés nem biztonsági tanúsítás. A felvételhez egy karbantartó jóváhagyása kell.
