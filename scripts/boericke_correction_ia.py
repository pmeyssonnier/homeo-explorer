# ============================================================
# Correction OCR assistée par IA : propositions à valider à la main
# Google Colab
# Entrée  : boericke_a_corriger.csv (produit par boericke_parser_complet.py)
#           boericke_remedies.json (facultatif : donne le contexte de chaque phrase)
# Sortie  : boericke_a_corriger.csv complété des colonnes
#           proposition_ia, confiance_ia, note_ia, valider
# L'IA ne remplit JAMAIS texte_corrige : tu valides en mettant « o » dans la colonne valider
# (ou tu écris ta propre version dans texte_corrige, qui reste prioritaire).
# Clé API : Colab > icône clé (Secrets) > ANTHROPIC_API_KEY, accès activé pour ce notebook.
# ============================================================

import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "anthropic"], check=False)

import os, re, json, time, difflib, hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

MODEL = "claude-sonnet-5-5"       # bon compromis qualité / coût pour ce travail
BATCH = 20                        # phrases par appel
WORKERS = 4                       # appels en parallèle
LIMIT = None                      # ex. 200 pour un premier essai sur les fiches les plus abîmées
CSV = "boericke_a_corriger.csv"
JSON_SRC = "boericke_remedies.json"
CACHE = "correction_ia_cache.json"      # reprise possible si la session Colab coupe
DRY_RUN = os.environ.get("DRY_RUN") == "1"   # test sans appel API

# ------------------------------------------------------------
# 0. Fichiers et clé
# ------------------------------------------------------------
if not os.path.exists(CSV):
    from google.colab import files
    print(f"Sélectionne {CSV} (et boericke_remedies.json si tu l'as, pour le contexte)")
    files.upload()
df = pd.read_csv(CSV, dtype=str, keep_default_na=False)
for col in ("proposition_ia", "confiance_ia", "note_ia", "valider"):
    if col not in df.columns:
        df[col] = ""
print(f"{len(df):,} phrases dans la feuille, {(df['texte_corrige'].str.strip() != '').sum()} déjà corrigées à la main")

sections = {}
if os.path.exists(JSON_SRC):
    for r in json.load(open(JSON_SRC, encoding="utf-8"))["remedies"]:
        sections[r["remedy"]] = r.get("sections", {})
    print(f"Contexte : {len(sections)} fiches chargées depuis {JSON_SRC}")

if not DRY_RUN:
    try:
        from google.colab import userdata
        api_key = userdata.get("ANTHROPIC_API_KEY")
    except Exception:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        from getpass import getpass
        api_key = getpass("Clé API Anthropic : ")
    import anthropic
    client = anthropic.Anthropic(api_key=api_key, max_retries=6)

cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
key_of = lambda remedy, section, txt: hashlib.sha1(f"{remedy}|{section}|{txt}".encode()).hexdigest()

# ------------------------------------------------------------
# 1. Consigne
# ------------------------------------------------------------
SYSTEM = """Tu corriges des erreurs de reconnaissance de caractères (OCR) dans le texte anglais du
« Pocket Manual of Homoeopathic Materia Medica » de William Boericke (3e édition, 1906), scanné par l'Internet Archive.

Règles strictes :
- Corrige uniquement les erreurs d'OCR : lettres confondues (rn/m, li/h, I/l, 0/o, f/s…), mots coupés ou collés,
  césures de fin de ligne restées dans le texte, ponctuation abîmée, caractères parasites (^ * » ■ etc.).
- Garde l'orthographe et le vocabulaire de 1906 (haemorrhoids, oedema, diarrhoea, catarrh, coryza, faeces…).
  Ne modernise pas, ne reformule pas, ne traduis pas.
- N'ajoute aucune information et n'en retire aucune. Si un mot est illisible et que le contexte ne permet pas
  de le retrouver avec certitude, laisse-le tel quel.
- Les renvois entre crochets sont des abréviations de remèdes de Boericke : restitue-les sous leur forme
  habituelle (ex. « [Bry.; Merc] » -> « [Bry.; Merc.] », « [Puis.] » -> « [Puls.] »).
- confiance : "haute" si la correction est évidente, "moyenne" si probable, "faible" si tu as dû deviner
  ou laisser des parties illisibles.
- note : quelques mots en français si quelque chose reste douteux, sinon chaîne vide.

Réponds uniquement par un tableau JSON, sans texte autour :
[{"id": <id>, "corrige": "<texte corrigé>", "confiance": "haute|moyenne|faible", "note": "<...>"}]"""

def build_prompt(remedy, section, items):
    ctx = sections.get(remedy, {}).get(section, "")
    parts = [f"Remède : {remedy}\nSection : {section}"]
    if ctx:
        parts.append("Texte complet de la section (contexte, ne pas corriger) :\n" + ctx[:2500])
    parts.append("Phrases à corriger :\n" + json.dumps([{"id": i, "texte": t} for i, t in items], ensure_ascii=False))
    return "\n\n".join(parts)

def parse_answer(text):
    m = re.search(r"\[.*\]", text, re.S)
    return json.loads(m.group(0)) if m else []

# ------------------------------------------------------------
# 2. Appels
# ------------------------------------------------------------
todo = df[(df["texte_corrige"].str.strip() == "") & (df["proposition_ia"].str.strip() == "")]
if LIMIT:
    todo = todo.head(LIMIT)
jobs = []
for (remedy, section), g in todo.groupby(["remedy", "section"], sort=False):
    rows = [(idx, t) for idx, t in zip(g.index, g["texte_ocr"]) if key_of(remedy, section, t) not in cache]
    for k in range(0, len(rows), BATCH):
        jobs.append((remedy, section, rows[k:k + BATCH]))
print(f"À traiter : {sum(len(j[2]) for j in jobs):,} phrases en {len(jobs)} appels "
      f"({len(todo) - sum(len(j[2]) for j in jobs):,} déjà en cache)")

def run(job):
    remedy, section, rows = job
    items = [(i, t) for i, (_, t) in enumerate(rows)]
    if DRY_RUN:
        answer = [{"id": i, "corrige": re.sub(r"[\^*»■]", "", t), "confiance": "moyenne", "note": "test"} for i, t in items]
    else:
        msg = client.messages.create(model=MODEL, max_tokens=8000, system=SYSTEM,
                                     messages=[{"role": "user", "content": build_prompt(remedy, section, items)}])
        answer = parse_answer("".join(b.text for b in msg.content if getattr(b, "type", "") == "text"))
    out = {}
    for a in answer:
        try:
            i = int(a["id"])
            out[key_of(remedy, section, rows[i][1])] = {
                "corrige": str(a.get("corrige", "")).strip(),
                "confiance": a.get("confiance", ""), "note": a.get("note", "")}
        except (KeyError, ValueError, IndexError, TypeError):
            continue
    return out

t0, done = time.time(), 0
with ThreadPoolExecutor(max_workers=WORKERS) as ex:
    futures = [ex.submit(run, j) for j in jobs]
    for n, f in enumerate(as_completed(futures), 1):
        try:
            cache.update(f.result())
        except Exception as e:
            print("  appel en échec (sera repris au prochain lancement) :", str(e)[:120])
        if n % 10 == 0 or n == len(futures):
            json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
            print(f"  {n}/{len(futures)} appels ({time.time() - t0:.0f} s)")

# ------------------------------------------------------------
# 3. Report dans la feuille + garde-fous
# ------------------------------------------------------------
n_prop = 0
for idx, row in df.iterrows():
    c = cache.get(key_of(row["remedy"], row["section"], row["texte_ocr"]))
    if not c or not c["corrige"]:
        continue
    note, conf = c["note"], c["confiance"]
    sim = difflib.SequenceMatcher(None, row["texte_ocr"], c["corrige"]).ratio()
    if sim < 0.6:                                  # trop différent de l'original : à regarder de près
        conf = "faible"
        note = (note + " ; " if note else "") + f"modification importante (similarité {sim:.2f})"
    if c["corrige"] == row["texte_ocr"]:
        note = (note + " ; " if note else "") + "aucun changement proposé"
    df.at[idx, "proposition_ia"] = c["corrige"]
    df.at[idx, "confiance_ia"] = conf
    df.at[idx, "note_ia"] = note
    n_prop += 1

df.to_csv(CSV, index=False, encoding="utf-8-sig")
print(f"\nPropositions écrites : {n_prop:,} / {len(df):,}")
print(df["confiance_ia"].replace("", "(aucune)").value_counts().to_string())
print("\nExemples :")
for _, r in df[df["proposition_ia"] != ""].head(5).iterrows():
    print(f"  [{r['confiance_ia']}] {r['remedy']} / {r['section']}\n    OCR : {r['texte_ocr'][:110]}\n    IA  : {r['proposition_ia'][:110]}")
print("\nÀ faire : ouvrir la feuille, mettre « o » dans « valider » pour chaque proposition acceptée "
      "(ou écrire ta version dans « texte_corrige »), puis relancer boericke_parser_complet.py avec la feuille.")

try:
    from google.colab import files
    files.download(CSV)
except Exception:
    pass
