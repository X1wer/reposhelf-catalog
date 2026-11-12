# A katalógus sémája – schemaVersion 1

> Állapot: első változat (2. munkamenet). A repó publikus címe még ideiglenes (`X1wer/reposhelf-catalog`), a nyilvános közzététel előtt véglegesítjük.

A katalógus a GitHubon tárolt, nyilvános alkalmazáslista. **Csak a kereséshez és az azonosításhoz szükséges minimális adatot** tartalmazza. Leírás, README, ikon, képernyőkép és APK nincs benne: ezeket az alkalmazás közvetlenül a megadott repóból kéri le.

**A katalógusban szereplés nem biztonsági tanúsítás.**

## Fájlok

| Fájl | Szerep |
|---|---|
| `apps/<id>.json` | Egy alkalmazás bejegyzése. A beküldők ezt szerkesztik (fájlonként egy app → kevés merge-ütközés). |
| `categories.json` | A rögzített kategória-azonosítók listája. |
| `schema/app-entry.v1.schema.json` | Egy bejegyzés JSON Schema-leírása (draft 2020-12). |
| `schema/catalog.v1.schema.json` | Az összeállított katalógus JSON Schema-leírása. |
| `dist/v1/catalog.json` | Az összeállított katalógus, amit az alkalmazás letölt. Generált fájl, kézzel nem szerkesztjük. |
| `tools/build_catalog.py` | Validálja a bejegyzéseket, és összeállítja a `dist/v1/catalog.json`-t. |

## Az összeállított katalógus (`dist/v1/catalog.json`)

```json
{
  "schemaVersion": 1,
  "catalogSerial": 1,
  "generatedAt": "2026-11-10T00:00:00Z",
  "expiresAt": "2027-02-08T00:00:00Z",
  "apps": [ { "...": "bejegyzések, id szerint rendezve" } ]
}
```

| Mező | Kötelező | Jelentés |
|---|---|---|
| `schemaVersion` | igen | A séma fő verziója. A kliens csak az általa ismert fő verziót dolgozza fel (lásd lent). |
| `catalogSerial` | igen | Monoton növekvő egész szám. A kliens a már elfogadottnál kisebb sorszámú katalógust elutasítja (visszagörgetés elleni védelem). Azonos sorszám csak azonos tartalommal fogadható el. |
| `generatedAt` | igen | Az összeállítás ideje (ISO-8601, UTC). |
| `expiresAt` | igen | Eddig tekinthető frissnek a katalógus. Utána a kliens figyelmeztet, hogy a katalógus elavult lehet, de böngészhető marad. |
| `apps` | igen | A bejegyzések listája (legfeljebb 20 000). |

## Egy bejegyzés (`apps/<id>.json`)

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

| Mező | Kötelező | Szabály | Mire jó |
|---|---|---|---|
| `id` | igen | `^[a-z0-9][a-z0-9._-]{1,63}$`, egyedi, a fájlnévvel egyezik | Stabil katalógusazonosító. Publikálás után nem változtatható. |
| `name` | igen | 1–100 karakter | Megjelenített név, keresés. |
| `source.provider` | igen | jelenleg csak `github` | Forrásszolgáltató. Az ismeretlen szolgáltatójú bejegyzést a kliens kihagyja (előre-kompatibilitás). |
| `source.repository` | igen | `owner/name`, GitHub-névszabályok | A repó szöveges útvonala. |
| `source.repositoryId` | ajánlott | pozitív egész | A GitHub stabil repó-azonosítója. Ha a név alatt egyszer csak más azonosítójú repó jelenik meg (a régit törölték, és valaki újra létrehozta), a kliens nem frissít belőle (repojacking elleni védelem). |
| `packageName` | nem | Android-csomagnév | A várt csomagazonosító. Eltérés esetén a kliens nem telepít. |
| `signingCertSha256` | nem | legfeljebb 10 darab kisbetűs, 64 jegyű hex | A várt aláíró tanúsítvány(ok) ujjlenyomata. Ha meg van adva, ez erősebb az első telepítéskor rögzített („trust on first use”) aláírónál. |
| `minVersionCode` | nem | ≥ 0 | Ennél régebbi verziót a kliens nem telepít. |
| `keywords` | nem | legfeljebb 30 darab, egyenként 1–40 karakter | Keresési kulcsszavak, angolul és magyarul is. A kliens ékezet- és kis/nagybetű-függetlenül keres. |
| `category` | igen | a `categories.json` egyik eleme | Kategória. Az ismeretlen kategóriát a kliens `other`-ként kezeli. |
| `assetFilter` | nem | legfeljebb 200 karakteres reguláris kifejezés | Ha egy kiadás több változatot tartalmaz (pl. F-Droid- és GitHub-build), ez választja ki a telepíthető állományt. |

A katalógusba **nem** kerülhet leírás, README-részlet vagy más, harmadik féltől bemásolt szöveg. Ennek két oka van: a katalógusadatok licence (CC0-1.0), és a „minimális adat” elv. Az F-Droid és az IzzyOnDroid metaadatai AGPL-licencűek, onnan nem szabad adatot átvenni.

## Kompatibilitás és verziózás

- **Visszafelé kompatibilis bővítés** (új, opcionális mező): a `schemaVersion` nem változik, a régi kliensek az ismeretlen mezőt figyelmen kívül hagyják.
- **Nem kompatibilis változás:** új fő verzió (`schemaVersion: 2`), **új útvonalon** (`dist/v2/catalog.json`). Az átmeneti időszakban a `dist/v1/` is frissül, így a régi kliensek tovább működnek.
- Ha egy kliens a támogatottnál újabb `schemaVersion`-t kap, nem dolgozza fel. Megtartja az utolsó érvényes katalógust, és jelzi, hogy frissíteni kell az alkalmazást.
- A hibás bejegyzést a kliens egyenként kihagyja. Ha a hibás bejegyzések aránya 20% fölött van, az egész katalógust elutasítja, és az előző marad érvényben.

## Aláírás

A `dist/v1/catalog.json` mellett leválasztott aláírás van: `dist/v1/catalog.json.sig`. Az aláírás a katalógusfájl **pontos bájtjaira** vonatkozik (a `.gitattributes` LF-sorvéget rögzít, a `.sig` bináris).

```json
{"format": 1, "signatures": [{"keyId": "catalog-2026-a", "algorithm": "ecdsa-p256-sha256", "value": "<base64 DER>"}]}
```

- Algoritmus: ECDSA P-256 / SHA-256, DER-kódolt aláírás, base64. Ismeretlen `algorithm` értékű aláírást a kliens kihagy.
- Több aláírás is lehet (kulcsrotáció). A kliens akkor fogadja el a katalógust, ha legalább egy, az alkalmazásba fordított nyilvános kulccsal (`keyId` → kulcs) készült aláírás érvényes. Hiányzó vagy érvénytelen aláírásnál a korábbi érvényes katalógus marad.
- A nyilvános kulcsok: `keys/<keyId>.pub` (PEM, SubjectPublicKeyInfo). A privát kulcs soha nem kerül a repóba.
- Aláírás: `python tools/sign_catalog.py --key <keyId>=<a privát kulcs útvonala a repón kívül>`; ellenőrzés: `python tools/validate_catalog.py --require-signature`.
- **Jelenleg teszt-kulcs** (`catalog-test-2026a`) írja alá a katalógust. A valódi kulcs létrehozásáról és tárolásáról a karbantartó dönt (Q-006).
