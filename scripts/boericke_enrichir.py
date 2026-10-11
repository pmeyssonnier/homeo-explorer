# ============================================================
# Enrichissement de boericke_remedies.json
#   1. Traduction française phrase par phrase (MarianMT, local et gratuit)
#   2. Statut dans la Base de données publique des médicaments (BDPM, France)
# Google Colab - activer le GPU : Exécution > Modifier le type d'exécution > GPU T4
# Entrée  : boericke_remedies.json (produit par boericke_parser_complet.py)
# Sortie  : boericke_remedies_fr.json (à charger dans homeo-explorer.html)
# ============================================================

import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "transformers", "sentencepiece", "sacremoses"], check=False)

import re, json, io, os, time, unicodedata
import requests, pandas as pd, torch

# ------------------------------------------------------------
# 0. Chargement du JSON Boericke
# ------------------------------------------------------------
SRC = "boericke_remedies.json"
if not os.path.exists(SRC):
    from google.colab import files
    print("Sélectionne boericke_remedies.json")
    files.upload()
data = json.load(open(SRC, encoding="utf-8"))
remedies = data["remedies"]
print(f"{len(remedies)} remèdes chargés")

SKIP_SECTIONS = {"dose", "extra homoeopathic uses", "relationship", "modalities"}

def split_sentences(txt):
    """Même découpage que l'application, renvois [Acon.] retirés."""
    out = []
    protected = re.sub(r"\[[^\]]*\]", lambda m: m.group(0).replace(";", "¦").replace(".", "·"), txt)
    for s in re.split(r"(?<=[\.;])\s+(?=[A-Z])", protected):
        s = re.sub(r"\[[^\]]*\]", "", s.replace("¦", ";").replace("·", ".")).strip(" ;")
        if len(s) > 3:
            out.append(s)
    return out

# ------------------------------------------------------------
# 1. Traduction (MarianMT opus-mt-en-fr) avec cache reprenable
# ------------------------------------------------------------
from transformers import MarianMTModel, MarianTokenizer

MODEL = "Helsinki-NLP/opus-mt-en-fr"
device = "cuda" if torch.cuda.is_available() else "cpu"
print("Appareil :", device, "(sans GPU, compter plusieurs heures)" if device == "cpu" else "")
tok = MarianTokenizer.from_pretrained(MODEL)
model = MarianMTModel.from_pretrained(MODEL).to(device).eval()
if device == "cuda":
    model = model.half()

CACHE = "traductions_cache.json"
cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
print(f"Cache : {len(cache):,} traductions déjà faites")

def translate_batch(texts):
    enc = tok(texts, return_tensors="pt", padding=True, truncation=True, max_length=256).to(device)
    with torch.no_grad():
        out = model.generate(**enc, num_beams=2, max_new_tokens=256)
    return tok.batch_decode(out, skip_special_tokens=True)

# Tous les textes à traduire (sans doublons)
todo = set()
for r in remedies:
    for sec, txt in r["sections"].items():
        if sec not in SKIP_SECTIONS:
            todo.update(split_sentences(txt))
    todo.update(x for x in r.get("worse", []) + r.get("better", []) if x)
    if r.get("common_name"):
        todo.add(r["common_name"])
todo = sorted(t for t in todo if t not in cache)
print(f"À traduire : {len(todo):,} segments")

BATCH = 64 if device == "cuda" else 8
t0 = time.time()
todo.sort(key=len)                                   # lots de longueurs proches = plus rapide
for k in range(0, len(todo), BATCH):
    chunk = todo[k:k + BATCH]
    for src, dst in zip(chunk, translate_batch(chunk)):
        cache[src] = dst
    if (k // BATCH) % 20 == 0:
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
        done = k + len(chunk)
        rate = done / max(1, time.time() - t0)
        print(f"  {done:,}/{len(todo):,}  ({rate:.0f}/s, reste ~{(len(todo) - done) / max(rate, 1) / 60:.0f} min)")
json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
print("Traduction terminée")

for r in remedies:
    r["sentences"] = {sec: [[s, cache.get(s, s)] for s in split_sentences(txt)]
                      for sec, txt in r["sections"].items() if sec not in SKIP_SECTIONS}
    r["worse_fr"] = [cache.get(x, x) for x in r.get("worse", [])]
    r["better_fr"] = [cache.get(x, x) for x in r.get("better", [])]
    r["common_name_fr"] = cache.get(r.get("common_name", ""), r.get("common_name", ""))

# ------------------------------------------------------------
# 2. BDPM : la souche est-elle enregistrée en France ?
# ------------------------------------------------------------
BDPM = "https://base-donnees-publique.medicaments.gouv.fr/download/file/"

def bdpm_read(fname, cols):
    content = requests.get(BDPM + fname, timeout=120).content
    try:
        txt = content.decode("utf-8")
    except UnicodeDecodeError:
        txt = content.decode("latin-1")
    df = pd.read_csv(io.StringIO(txt), sep="\t", header=None, dtype=str, on_bad_lines="skip")
    df = df.iloc[:, :len(cols)]
    df.columns = cols[:df.shape[1]]
    print(f"BDPM {fname} : {len(df):,} lignes")
    return df

cis = bdpm_read("CIS_bdpm.txt", ["cis", "denomination", "forme", "voies", "statut_amm", "procedure",
                                 "etat", "date_amm", "statut_bdm", "num_eu", "titulaires", "surveillance"])
compo = bdpm_read("CIS_COMPO_bdpm.txt", ["cis", "element", "code_substance", "substance",
                                         "dosage", "ref_dosage", "nature", "liaison"])

homeo = cis[cis["procedure"].str.contains("hom", case=False, na=False)]
print(f"Spécialités homéopathiques : {len(homeo):,}")

def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper()
    s = re.sub(r"POUR PREPARATIONS? HOMEOPATHIQUES?|TEINTURE MERE|SOUCHE", " ", s)
    return re.sub(r"[^A-Z ]", " ", s).split()

# Noms de souches côté BDPM : début de la dénomination + substances de la composition
names = {}
for _, row in homeo.iterrows():
    names.setdefault(row["cis"], set()).add(" ".join(norm(str(row["denomination"]).split(",")[0])))
for _, row in compo[compo["cis"].isin(homeo["cis"])].iterrows():
    names.setdefault(row["cis"], set()).add(" ".join(norm(row["substance"])))
info = homeo.set_index("cis")[["denomination", "etat"]].to_dict("index")

def match_bdpm(remedy_name):
    key = " ".join(norm(re.sub(r"\(.*?\)", "", remedy_name)))
    if not key:
        return []
    hits = []
    for cis_id, ns in names.items():
        if any(n == key or n.startswith(key + " ") for n in ns):
            hits.append(cis_id)
    return hits

n_found = 0
for r in remedies:
    hits = match_bdpm(r["remedy"])
    comm = [h for h in hits if "Commercialis" in str(info[h]["etat"]) and "Non" not in str(info[h]["etat"])]
    r["bdpm"] = {
        "specialites": len(hits),
        "commercialisees": len(comm),
        "exemples": sorted({str(info[h]["denomination"]).split(",")[0].strip() for h in (comm or hits)})[:3],
    }
    n_found += bool(hits)
print(f"Souches Boericke trouvées dans la BDPM : {n_found} / {len(remedies)}")
for name in ("Arnica", "Natrum Muriaticum", "Murex", "Chaparro Amargoso"):
    r = next((x for x in remedies if x["remedy"].startswith(name)), None)
    if r:
        print(f"  {r['remedy']:22} -> {r['bdpm']['specialites']} spécialité(s), "
              f"{r['bdpm']['commercialisees']} commercialisée(s) {r['bdpm']['exemples'][:2]}")

# ------------------------------------------------------------
# 3. Export
# ------------------------------------------------------------
data["source"]["traduction"] = "Traduction automatique MarianMT (Helsinki-NLP/opus-mt-en-fr), non relue"
data["source"]["bdpm"] = "Base de données publique des médicaments, base-donnees-publique.medicaments.gouv.fr"
data["source"]["bdpm_date"] = time.strftime("%Y-%m-%d")
OUT = "boericke_remedies_fr.json"
json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
print(f"Écrit : {OUT} ({os.path.getsize(OUT) / 1e6:.1f} Mo)")

r = next((x for x in remedies if x["remedy"].startswith("Aconitum")), None)
if r:
    print("\nExemple Aconitum :")
    for en, fr in r["sentences"].get("mind", [])[:3]:
        print(f"  EN : {en}\n  FR : {fr}")

from google.colab import files
files.download(OUT)
