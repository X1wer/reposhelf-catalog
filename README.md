# RepoShelf katalógus

> Munkanév, fejlesztés alatt. A teljes dokumentáció a 10. munkamenetben készül el.

GitHubon közzétett, nyílt forráskódú Android-alkalmazások kereshető, minimális katalógusa a RepoShelf alkalmazáskezelőhöz. A katalógus csak nevet, repó-útvonalat, kulcsszavakat és kategóriát tartalmaz. Minden más adatot az alkalmazás közvetlenül a repókból kér le.

- Séma: [docs/SCHEMA.md](docs/SCHEMA.md)
- Beküldés és jóváhagyás: [docs/SUBMISSION.md](docs/SUBMISSION.md)
- Összeállítás: `python tools/build_catalog.py --serial <N>` · Aláírás: `python tools/sign_catalog.py --key <keyId>=<útvonal>` · Validáció: `python tools/validate_catalog.py` · Tesztek: `python -m unittest discover -s tools`
- A katalógust jelenleg **teszt-kulcs** írja alá (`keys/catalog-test-2026a.pub`); a valódi kulcsról a karbantartó dönt.

**A katalógusban szereplés nem biztonsági tanúsítás.**

Licenc (jóváhagyva, a LICENSE fájlok a 10. munkamenetben kerülnek a repóba): a katalógusadatokra CC0-1.0, a szkriptekre Apache-2.0.
