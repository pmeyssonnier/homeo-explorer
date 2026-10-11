# ============================================================
# Contrôle qualité par échantillon - étape 1 : tirer l'échantillon
# Entrée : boericke_remedies.json   Sortie : controle_echantillon.csv
# ============================================================
import json, random, re, os
import pandas as pd
from urllib.parse import quote

SRC = "boericke_remedies.json"
N_PAR_STRATE = 50          # 50 contrôles par strate (6 strates = 300 lignes, ~2 à 3 h)
GRAINE = 2026              # même graine = même échantillon (reproductible)

if not os.path.exists(SRC):
    from google.colab import files
    files.upload()
data = json.load(open(SRC, encoding="utf-8"))
R = data["remedies"]
SCAN = "https://archive.org/details/pocketmanualhom00boergoog"

def lien_scan(txt):
    # recherche plein texte dans le scan avec 4 mots distinctifs de la phrase
    mots = [w for w in re.findall(r"[A-Za-z]{5,}", txt)][:4]
    return f'{SCAN}?q={quote(" ".join(mots))}' if mots else SCAN

strates = {k: [] for k in ("correction_ocr", "phrase_fiable", "phrase_a_verifier",
                           "limite_remede", "posologie_retiree", "nom_remede")}
for r in R:
    pages = r["source_ref"]["pages"]
    base = {"remedy": r["remedy"], "pages": pages}
    for c in r.get("corrections_ocr") or []:
        strates["correction_ocr"].append({**base, "section": c["section"], "a_controler": c["apres"],
            "contexte": "OCR d'origine : " + c["avant"], "question": "Le texte corrigé est-il exactement celui du scan de 1906 ?",
            "scan": lien_scan(c["apres"])})
    for sec, pairs in (r.get("lines") or {}).items():
        for s, q in pairs:
            k = "phrase_fiable" if q >= 0.9 else ("phrase_a_verifier" if q >= 0.75 else None)
            if k:
                strates[k].append({**base, "section": sec, "a_controler": s, "contexte": f"score OCR {q}",
                    "question": "Phrase fidèle au scan, dans la bonne section et le bon remède ?", "scan": lien_scan(s)})
    secs = [k for k in r["sections"] if k not in ("dose", "extra homoeopathic uses")]
    if secs:
        debut = r["sections"][secs[0]][:200]
        fin = r["sections"][secs[-1]][-200:]
        strates["limite_remede"].append({**base, "section": f"{secs[0]} … {secs[-1]}", "a_controler": "DÉBUT : " + debut,
            "contexte": "FIN : " + fin, "question": "Le début et la fin appartiennent-ils bien à ce remède (pas au voisin) ?",
            "scan": lien_scan(debut)})
    for sec, items in (r.get("posologie_hors_dose") or {}).items():
        for s in items:
            strates["posologie_retiree"].append({**base, "section": sec, "a_controler": s, "contexte": "retiré du texte affiché",
                "question": "Est-ce bien une posologie / un usage (et non un symptôme) ?", "scan": lien_scan(s)})
    strates["nom_remede"].append({**base, "section": "", "a_controler": f'{r["remedy"]} ({r.get("common_name", "")})',
        "contexte": "en-tête OCR : " + r["source_ref"].get("entete_ocr", ""),
        "question": "Nom latin et nom commun conformes au scan ?", "scan": r["source_ref"]["url"]})

random.seed(GRAINE)
rows = []
for k, pop in strates.items():
    tir = random.sample(pop, min(N_PAR_STRATE, len(pop)))
    for x in tir:
        rows.append({"strate": k, "population": len(pop), **x, "verdict": "", "commentaire": ""})
    print(f"{k:20} population {len(pop):6,}  échantillon {len(tir)}")
ech = pd.DataFrame(rows)
ech.to_csv("controle_echantillon.csv", index=False, encoding="utf-8-sig")
print("\nRemplir la colonne verdict : ok / erreur  (laisser vide si pas contrôlé)")
try:
    from google.colab import files
    files.download("controle_echantillon.csv")
except Exception:
    pass
