import bisect
import csv
import datetime
import io
import json
import os
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (ceny-paliv-dashboard)"}
FP = "https://www.fuel-prices.eu"
SOUSEDE = [("Německo", "Germany"), ("Rakousko", "Austria"), ("Slovensko", "Slovakia"),
           ("Polsko", "Poland"), ("Maďarsko", "Hungary")]


def stahni(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def nacti_dosavadni(cesta):
    with open(cesta, encoding="utf-8-sig") as f:
        text = f.read()
    if text.lstrip().startswith("["):
        radky = json.loads(text)
    else:
        radky = list(csv.DictReader(io.StringIO(text)))
    return {r["tyden"]: {k: (r[k] if k == "tyden" else float(r[k])) for k in r} for r in radky}


def ceny_eu(zeme):
    fp = json.loads(stahni(f"{FP}/{zeme}/?format=json"))["fp"]
    p = {x["fuel_code"]: x["mean"] for x in fp["prices"] if x["currency"] == "EUR"}
    return fp["facts"]["Week (price date)"], p["E5"], p["B7"]


def main():
    dosavadni_cesta, vystup = sys.argv[1], sys.argv[2]
    stare = nacti_dosavadni(dosavadni_cesta)
    if len(stare) < 100:
        sys.exit(f"Dosavadní soubor má jen {len(stare)} týdnů, končím, abych nepřišel o historii.")

    hist = json.loads(stahni(f"{FP}/Czechia/cs?format=json&history=520w"))["fp"]["history"]
    if hist["unit"] != "EUR/L" or hist["columns"] != ["date", "petrol_E5", "diesel_B7"]:
        sys.exit(f"Zdroj změnil formát: {hist['unit']} {hist['columns']}")
    nove = [r for r in hist["rows"] if r[1] and r[2]]

    od = (datetime.date.fromisoformat(min(r[0] for r in nove)) - datetime.timedelta(days=10)).isoformat()
    ecb = stahni("https://data-api.ecb.europa.eu/service/data/EXR/D.CZK.EUR.SP00.A"
                 f"?format=csvdata&startPeriod={od}&detail=dataonly")
    kurzy = sorted((r["TIME_PERIOD"], float(r["OBS_VALUE"])) for r in csv.DictReader(io.StringIO(ecb)))
    dny = [d for d, _ in kurzy]

    def kurz(den):
        i = bisect.bisect_right(dny, den) - 1
        if i < 0:
            sys.exit(f"Chybí kurz ECB pro {den}")
        return kurzy[i][1]

    spojene = dict(stare)
    for den, n95, naf in nove:
        k = kurz(den)
        spojene[den] = {"tyden": den, "natural95": round(n95 * k, 2), "nafta": round(naf * k, 2),
                        "natural95_eur": n95, "nafta_eur": naf, "kurz_czk_eur": k}
    radky = [spojene[d] for d in sorted(spojene)]
    for r in radky:
        if not (15 < r["natural95"] < 90 and 15 < r["nafta"] < 90):
            sys.exit(f"Podezřelá cena v týdnu {r['tyden']}: {r['natural95']} / {r['nafta']}")

    posledni = radky[-1]
    k = kurz(posledni["tyden"])
    sousede = [{"zeme": "Česko", "natural95": posledni["natural95"], "nafta": posledni["nafta"],
                "natural95_eur": posledni["natural95_eur"], "nafta_eur": posledni["nafta_eur"],
                "tyden": posledni["tyden"]}]
    for cz, en in SOUSEDE:
        tyden, e5, b7 = ceny_eu(en)
        if tyden != posledni["tyden"]:
            continue
        sousede.append({"zeme": cz, "natural95": round(e5 * k, 2), "nafta": round(b7 * k, 2),
                        "natural95_eur": e5, "nafta_eur": b7, "tyden": tyden})

    os.makedirs(vystup, exist_ok=True)
    with open(os.path.join(vystup, "ceny-paliv-cr.json"), "w", encoding="utf-8") as f:
        json.dump(radky, f, ensure_ascii=False)
    with open(os.path.join(vystup, "sousede.json"), "w", encoding="utf-8") as f:
        json.dump(sousede, f, ensure_ascii=False)
    print(json.dumps({
        "posledni_tyden": posledni["tyden"],
        "dosavadni_posledni_tyden": max(stare),
        "novych_tydnu": len(set(spojene) - set(stare)),
        "tydnu_celkem": len(radky),
        "natural95": posledni["natural95"], "nafta": posledni["nafta"],
        "sousede": [s["zeme"] for s in sousede],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
