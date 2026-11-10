# RepoShelf katalógus

> Munkanév, fejlesztés alatt. A teljes dokumentáció a 10. munkamenetben készül el.

GitHubon közzétett, nyílt forráskódú Android-alkalmazások kereshető, minimális katalógusa a RepoShelf alkalmazáskezelőhöz. A katalógus csak nevet, repó-útvonalat, kulcsszavakat és kategóriát tartalmaz. Minden más adatot az alkalmazás közvetlenül a repókból kér le.

- Séma: [docs/SCHEMA.md](docs/SCHEMA.md)
- Beküldés: [docs/SUBMISSION.md](docs/SUBMISSION.md) (vázlat)
- Összeállítás: `python tools/build_catalog.py --serial <N>` · Ellenőrzés: `python tools/build_catalog.py --check` · Tesztek: `python -m unittest discover -s tools`

**A katalógusban szereplés nem biztonsági tanúsítás.**

Licenc (jóváhagyva, a LICENSE fájlok a 10. munkamenetben kerülnek a repóba): a katalógusadatokra CC0-1.0, a szkriptekre Apache-2.0.
