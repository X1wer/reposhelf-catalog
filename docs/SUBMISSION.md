# Beküldési szabályok

## Mit lehet beküldeni?

Olyan nyílt forráskódú Android-alkalmazást, amely:

1. **nyilvános GitHub-repóban** van;
2. **GitHub Releases** formában közzétett, **telepíthető APK-t** ad ki (a forráskód jelenléte önmagában nem elég; AAB nem telepíthető);
3. a kiadott APK-kat **a fejlesztő saját kulcsával** írja alá. Nyilvános teszt- vagy debug-kulccsal aláírt kiadást nem veszünk fel, mert azzal bárki aláírhatna egy hamis frissítést;
4. **OSI- vagy FSF-elfogadott licencű**;
5. nem tartalmaz ismerten rosszindulatú működést, és nem kér az alapfunkciójához nem szükséges, rejtett jogosultságot.

**A katalógusban szereplés nem biztonsági tanúsítás.** A felvétel technikai és formai ellenőrzés, nem teljes biztonsági audit.

## Hogyan?

1. Forkold a repót, és hozz létre egy új fájlt: `apps/<id>.json` (a formátum: [SCHEMA.md](SCHEMA.md)).
2. Futtasd helyben: `python tools/validate_catalog.py` (és a tesztek: `python -m unittest discover -s tools`).
3. Nyiss Pull Requestet a sablon szerint. A leírásban szerepeljen:
   - a repó linkje, és hogy te vagy-e az alkalmazás fejlesztője;
   - ha ismered: a csomagazonosító (`packageName`) és az aláíró tanúsítvány SHA-256 ujjlenyomata (`signingCertSha256`), és honnan származik (pl. a fejlesztő által közzétett érték).
4. A `dist/` könyvtárat **ne** módosítsd: azt a karbantartók generálják és írják alá.

## Automatikus ellenőrzés (GitHub Actions, minden PR-on)

A `.github/workflows/validate.yml` a `tools/validate_catalog.py`-t futtatja. Ellenőrzi:

- a JSON-szintaxist és a sémát, a kötelező mezőket, az ismeretlen mezőket;
- az `id` egyediségét, és hogy a fájlnév egyezik vele;
- a repó-útvonal formátumát (`owner/name`, teljes URL nem fogadható el), és hogy a repó nem szerepel-e már más azonosító alatt;
- a metaadat-ellentmondásokat: ugyanaz a `packageName` vagy `repositoryId` két bejegyzésben, `minVersionCode` csomagnév nélkül, ismétlődő aláíró-ujjlenyomat vagy kulcsszó;
- az `assetFilter` megengedett alakját (korlátos futási idejű reguláris kifejezés, lásd [SCHEMA.md](SCHEMA.md)), a nevekben és kulcsszavakban a láthatatlan vagy irányváltó karaktereket, az ismétlődő JSON-kulcsokat;
- a `dist/v1/catalog.json` érvényességét, determinisztikus formáját és **az aláírását** (PR-on is: egy beküldés a `dist`-et nem módosítja, így a meglévő aláírás érvényes marad);
- a `keys/` mappa nyilvános kulcsait (csak szabályos P-256 kulcs lehet), és kiírja, mely kulcsok számítanak megbízhatónak, illetve melyik ellenőrizte az aláírást.

Az action commit SHA-hoz rögzített, a workflow csak olvasási jogot kap, titkot nem használ, és `pull_request` eseményre fut (nem `pull_request_target`-re).

**Mit NEM bizonyít a zöld pipa?** A PR a saját változatában lévő validátorral és workflow-val fut. Ha egy PR az `apps/` mappán kívül bármit módosít (`tools/`, `schema/`, `keys/`, `dist/`, `.github/`, `categories.json`), az automatikus ellenőrzés eredménye önmagában semmit nem ér: lásd a jóváhagyó teendőit.

## Emberi jóváhagyás

A sikeres automatikus ellenőrzés nem elég. Egy karbantartó (CODEOWNERS) kézzel ellenőrzi:

1. a repó létezik és nyilvános; a `repositoryId` egyezik a GitHub által közölttel (`https://api.github.com/repos/<owner>/<repo>` → `id`);
2. a legutóbbi kiadásokban van telepíthető APK, és az aláírója a fejlesztő saját kulcsa (`apksigner verify --print-certs`); ha a PR megad `signingCertSha256`-ot, az egyezik vele; ha `packageName`-et, az egyezik az APK-éval;
3. a licenc és a fenti feltételek teljesülnek, a név és a kulcsszavak nem utánoznak más alkalmazást (hasonló írásképű, pl. cirill betűkkel írt nevekre is figyelve);
4. **a PR csak az `apps/` mappát érinti.** Ha bármi mást is módosít:
   - `tools/`, `.github/`, `schema/`, `categories.json`: soronkénti átnézés; a zöld validáció ilyenkor nem bizonyíték, mert a PR a saját validátorát futtatta;
   - `keys/`: új vagy módosított nyilvános kulcsot beküldő PR-t **soha** nem olvasztunk be (a megbízható kulcsokról csak a karbantartó dönt; a validáció kimenete felsorolja, mely kulcsokat tekinti megbízhatónak);
   - `dist/`: beküldő nem módosíthatja; ha mégis, a PR-t elutasítjuk (a `dist`-et kizárólag a karbantartó állítja elő az `apps/`-ból);
5. meglévő bejegyzés `source` mezőjének módosítása (más repó ugyanazon `id` alatt) külön indoklást és ellenőrzést igényel: a kliens a már követett alkalmazásra nem alkalmazza a más repóra mutató bejegyzést, de az új telepítők az új repóból telepítenének.

Jóváhagyás után a karbantartó beolvasztja a PR-t, majd helyben (vagy a kulcs tárolásáról hozott döntés szerint) újragenerálja és aláírja a katalógust:

```
python tools/build_catalog.py --serial <a jelenleginél nagyobb szám>
python tools/sign_catalog.py --key <keyId>=<privát kulcs a repón kívül>
python tools/validate_catalog.py --require-signature
```

## A repó beállításai a nyilvános közzétételkor (a tulajdonos teendői)

Ezek a GitHub felületén állíthatók be, a repó tartalma nem tudja kikényszeríteni őket:

1. **A `main` ág védelme (branch protection / ruleset):** beolvasztás csak Pull Requesttel; legalább 1 jóváhagyás; „Require review from Code Owners”; „Dismiss stale approvals”; kötelező sikeres „Katalógus-validáció”; a force push és az ág törlése tiltva; a szabályok az adminisztrátorokra is vonatkozzanak (egyetlen karbantartónál ez a saját PR-okat is blokkolja: második karbantartó kell, vagy az adminisztrátori kivételt tudatosan, rögzítve kell vállalni).
2. **Actions:** az alapértelmezett `GITHUB_TOKEN` csak olvasási jogú; külső közreműködők workflow-ja csak jóváhagyás után fusson; csak a GitHub saját és a kifejezetten felsorolt, teljes commit SHA-hoz rögzített actionök engedélyezettek; a fork PR-ok nem kapnak titkot és írási jogot.
3. **Fiók:** kétlépcsős hitelesítés (lehetőleg hardverkulccsal) a tulajdonosi fiókon; secret scanning és push protection bekapcsolva.
4. **A repó és az alapértelmezett ág neve nem változhat:** a kliensbe a `…/reposhelf-catalog/main/dist/v1/catalog.json` cím van fordítva.
5. **Az aláíró workflow (a kulcs GitHub Actions secretben van):** a kulcs *environment secret* legyen egy védett környezetben (kötelező jóváhagyóval, csak a `main` ágról); a workflow csak `workflow_dispatch` vagy a `main`-re történő `push` eseményre fusson, soha PR-ra; a job maga állítsa elő a `dist`-et az `apps/`-ból, futtassa a teljes validációt, írjon alá, ellenőrizze vissza, és csak a két `dist` fájlt commitolja; a kulcs ideiglenes fájlba kerüljön (`umask 077`), `if: always()` lépés törölje, `set -x` és a titok kiírása nélkül; a sorszám az előző + 1 legyen; `concurrency` csoport akadályozza a párhuzamos futást.
6. **Kulcsmentés és -csere:** a privát kulcsról legyen offline mentés; a kulcscsere menete a [SCHEMA.md](SCHEMA.md) „Aláírás” részében.
7. **Az első nyilvános kiadás előtt:** a valódi kulcs létrehozása, a `keys/` és az alkalmazás kulcslistájának cseréje, újra-aláírás, a beépített katalógus frissítése. (Az alkalmazás release buildje a teszt-kulccsal szándékosan nem készíthető el.)

## Mit nem fogadunk el?

- Leírást, README-részletet vagy más, harmadik féltől bemásolt szöveget (a katalógusadatok CC0-1.0 alatt vannak).
- Adatot az F-Droid vagy az IzzyOnDroid metaadataiból (azok AGPL-licencűek).
- Más alkalmazást utánzó nevet vagy kulcsszavakat.

## Eltávolítás

Egy bejegyzés eltávolítható, ha a repó megszűnik, a kiadások már nem tartalmaznak APK-t, megváltozik az aláíró, és ezt a fejlesztő nem erősíti meg, vagy biztonsági probléma merül fel.
