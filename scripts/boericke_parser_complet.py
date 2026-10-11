# ============================================================
# Parser Boericke (version consolidée) - Pocket Manual of Homoeopathic Materia Medica
# 3e édition, 1906 (domaine public) - OCR Internet Archive
# Google Colab - Python 3
# Sorties : boericke_remedies.json, boericke_symptoms.csv,
#           boericke_review.csv (noms OCR à vérifier)
# Statut des données : USAGE TRADITIONNEL (1906), non validé cliniquement
# ============================================================

import re, os, json, difflib, unicodedata, requests
from collections import Counter
import pandas as pd

SRC_ID = "pocketmanualhom00boergoog"
SRC_URL = f"https://archive.org/download/{SRC_ID}/{SRC_ID}_djvu.txt"
SOURCE_META = {
    "title": "Pocket Manual of Homoeopathic Materia Medica, 3rd ed.",
    "author": "William Boericke",
    "year": 1906,
    "url": f"https://archive.org/details/{SRC_ID}",
    "digitization": "Google Books / Internet Archive (OCR)",
    "status": "Usage traditionnel - non validé cliniquement",
}

# ------------------------------------------------------------
# 1. Chargement du texte OCR
# ------------------------------------------------------------
def load_text():
    try:
        r = requests.get(SRC_URL, timeout=180)
        r.raise_for_status()
        print(f"Téléchargé : {len(r.text):,} caractères")
        return r.text
    except Exception as e:
        print("Téléchargement échoué :", e, "-> uploade le fichier _djvu.txt")
        from google.colab import files
        up = files.upload()
        return next(iter(up.values())).decode("utf-8", "replace")

raw = load_text()

# ------------------------------------------------------------
# 2. Règles de détection
# ------------------------------------------------------------
KNOWN_SECTIONS = [
    "mind", "head", "eyes", "ears", "nose", "face", "mouth", "teeth", "tongue",
    "throat", "stomach", "abdomen", "stool", "rectum", "urine", "urinary",
    "kidneys", "bladder", "male", "female", "sexual", "respiratory",
    "respiratory organs", "chest", "heart", "back", "neck", "extremities",
    "limbs", "sleep", "skin", "fever", "modalities", "relationship",
    "comparison", "dose", "gastric", "tissues", "nerves", "generalities",
    "larynx", "vision", "vertigo", "scalp", "glands", "blood", "circulation",
    "mind and head", "back and extremities", "head and stomach",
    "nose and throat", "extra homoeopathic uses",
]
DOSE_WORDS = re.compile(r"potenc|tinct|tritur|attenu|drop|dilut|grain|dose", re.I)
NOT_SECTIONS = {"worse", "better", "compare", "antidote", "antidotes", "complementary", "inimical"}
STOP_HEADERS = {"REPERTORY", "INDEX", "THERAPEUTIC INDEX", "LIST OF REMEDIES"}

SEC_RE = re.compile(
    r"^\s*[\W\d]{0,2}\s*([A-Z][A-Za-z&!$|{}\s\-]{1,40}?)"      # nom de section (OCR bruité)
    r"(\s*[\.\,\*»:;\}\)\!\$]*\s*(?:[—\-–=~]+|\^)[\s\^\-—–~=]*)"  # séparateur ". —", ".^-", "^"...
    r"(.*)$"
)

def upper_ratio(s):
    letters = [c for c in s if c.isalpha()]
    return sum(c.isupper() for c in letters) / len(letters) if letters else 0

def is_caps_line(s):
    s = s.strip()
    return sum(c.isalpha() for c in s) >= 3 and upper_ratio(s) >= 0.75

def next_nonempty(lines, i, maxgap=3):
    for j in range(i + 1, min(i + 1 + maxgap, len(lines))):
        if lines[j].strip():
            return j
    return None

def clean_caps(s):
    s = re.sub(r"[^A-Za-z\s\-]", "", s)
    return re.sub(r"\s+", " ", s).strip().upper()

PAREN_START = re.compile(r"^[^A-Za-z({[]{0,5}[A-Za-z]?[^A-Za-z({[]{0,4}[({[]")   # "(Musk.)", "^K (R^ ...", "- (Pennywort.)"

def is_remedy_header(lines, i):
    """NOM EN MAJUSCULES suivi d'une ligne '(Nom commun.)', parasites OCR tolérés."""
    l = lines[i].strip()
    if not is_caps_line(l) or len(l) > 45:
        return False
    if re.search(r"(^|\s)\d+(\s|$)", l):            # numéro de page isolé = titre courant
        return False
    j = next_nonempty(lines, i)
    return j is not None and bool(PAREN_START.match(lines[j].strip()))

def match_section(line):
    m = SEC_RE.match(line)
    if not m:
        return None
    if m.group(2) == "-":               # "Hip-joint", "Ear-ache" : mot composé
        return None
    name = re.sub(r"[^a-z ]", "", m.group(1).lower())
    name = re.sub(r"\s+", " ", name).strip()
    if not name or name in NOT_SECTIONS:
        return None
    if re.fullmatch(r"(?:[pbdhjno]|if)\s?[oa]\s?[sz]\s?[ec]", name):   # Pose, Bose, Jose, Ifase / Hose, Ifose
        if name.replace(" ", "") in ("nose", "dose"):         # lu correctement : on le croit
            return (name.replace(" ", ""), m.group(3))
        if re.search(r"potenc|tinct|tritur|attenu|dilut|grain|\bdoses?\b", m.group(3), re.I):
            return ("dose", m.group(3))                          # ('drops into throat' = Nose)
        return ("nose" if name[0] in "nh" or name.replace(" ", "").startswith("ifo") else "dose", m.group(3))
    dash = re.search(r"[—\-–=~]", m.group(2))
    best = difflib.get_close_matches(name, KNOWN_SECTIONS, n=1, cutoff=0.65 if dash else 0.8)
    return (best[0], m.group(3)) if best else None

def ocr_clean(s):
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\^(?=\s)", ",", s)     # "hungry^ faint" -> "hungry, faint"
    s = re.sub(r"[\^»■•«]", "", s)
    s = s.replace("{", "[").replace("}", "]")
    return re.sub(r"\s+", " ", s).strip()

def join_lines(lines):
    out = ""
    for l in lines:
        l = l.strip()
        if not l:
            continue
        if out.endswith("-") and l[:1].islower():   # césure de fin de ligne
            out = out[:-1] + l
        else:
            out = (out + " " + l).strip()
    return ocr_clean(out)

def best_spelling(header, running_headers):
    """Nom OCR abîmé -> orthographe majoritaire dans les en-têtes de page."""
    target = clean_caps(header)
    n = len(target.split())
    votes = Counter()
    for rh in running_headers:
        words = clean_caps(rh).split()
        for k in range(len(words) - n + 1):
            cand = " ".join(words[k:k + n])
            if difflib.SequenceMatcher(None, target, cand).ratio() >= 0.7:
                votes[cand] += 1
    return votes.most_common(1)[0][0] if votes else target

def page_number(s):
    """Numéro de page lu dans un titre courant : '2  ABIES ...' ou '... NAPELLUS.  9'."""
    m = re.match(r"^\s*(\d{1,4})\s+[A-Z]", s) or re.search(r"[A-Z\.,]\s+(\d{1,4})\s*$", s)
    return int(m.group(1)) if m else None

def page_number_loose(s):
    """Comme page_number, en tolérant o/O->0 et l/I->1 dans le nombre ('4o6 LYCOFODIUMi')."""
    m = re.match(r"^\s*([\doOlI]{2,4})\s+[A-Z]", s) or re.search(r"[A-Z\.,]\s+([\doOlI]{2,4})\s*$", s)
    if not m or not any(c.isdigit() for c in m.group(1)):
        return None
    return int(m.group(1).translate(str.maketrans("oOlI", "0011")))

# En-têtes ET noms communs illisibles : début du texte du remède suivant, repéré à la main
FORCED_SPLITS = [
    # (début du texte du remède manquant, nom du remède, nom commun)
    ("Acts on circular", "Cactus Grandiflorus", "Night-blooming Cereus"),
    ("Produces the most remarkable", "Cannabis Indica", "Hashish"),
]
# Début du répertoire : MOT EN MAJUSCULES suivi d'un tiret ("AWKWARD— Let things fall…")
REPERTORY_RE = re.compile(r"(?<![A-Za-z])[A-Z][A-Z£:]{3,}[^\sa-z]{0,2}\s*[—–-]")

def is_stop_header(s):
    c = clean_caps(s)
    return c in STOP_HEADERS or difflib.SequenceMatcher(None, c, "REPERTORY").ratio() >= 0.8

COMMON_HINT = re.compile(r"[(){}\[\]]")

def loose_header(lines, i):
    """En-tête abîmé reconnu en fin de remède : nom court suivi d'un nom commun court.
    Couvre 'ERioDicxyoir.' + '(Yerba …', 'JALAPA.' + 'aalapO', 'SEPIA.' + '^^^m. CXnky … Cuttlefish.)'."""
    l = lines[i].strip()
    if re.search(r"(^|\s)\d+(\s|$)", l) or len(l) > 40:
        return None
    core = re.sub(r"^[^A-Za-z]+|[^A-Za-z]+$", "", l)
    words = core.split()
    if not (1 <= len(words) <= 3) or not re.fullmatch(r"[A-Za-z\-\s]+", core) or len(core) < 4:
        return None
    if DOSE_WORDS.search(core):                    # fin de Dose ('rer potencies.'), pas un nom
        return None
    if not (is_caps_line(l) or l.rstrip()[-1:] in ".,"):
        return None
    j = next_nonempty(lines, i)
    if j is None:
        return None
    nxt = lines[j].strip()
    if len(nxt) > 40 or re.fullmatch(r"[\dIlOoi|]{1,4}[a-z]?\.?", nxt.replace(" ", "")):
        return None
    if not (COMMON_HINT.search(nxt) or (is_caps_line(l) and len(nxt) <= 12)):
        return None
    if match_section(nxt):
        return None
    k = next_nonempty(lines, j)                    # puis un paragraphe d'introduction
    if k is None or match_section(lines[k]):
        return None
    return j

def same_remedy(header_line, cur_header):
    """Le titre courant de page mentionne-t-il le remède en cours ?
    Tolère les abréviations ('CALC PHOS.' pour Calcarea), les lettres espacées
    ('R ATA N HI A') et le bruit OCR en tête de l'en-tête du remède ('I BORICUM')."""
    words = [w for w in clean_caps(cur_header.replace("[LOST]", "").replace("[SPLIT]", "").replace("[GAP]", "")).split()
             if len(w) >= 3]
    ref = words[0] if words else ""
    if not ref:
        return False
    body = re.sub(r"^\s*\d+\s+|\s+\d+\s*$", "", header_line)
    toks = [t for t in clean_caps(body).split() if len(t) >= 4]
    toks += [re.sub(r"[^A-Z]", "", seg.upper()) for seg in re.split(r"[—–^]|\s-\s", body)]   # segments recollés
    for t in toks:
        if len(t) < 4:
            continue
        if difflib.SequenceMatcher(None, ref, t).ratio() >= 0.75:
            return True
        if ref.startswith(t[:4]) and (ref.startswith(t) or difflib.SequenceMatcher(None, ref[:len(t)], t).ratio() >= 0.75):
            return True
    return False

def mid_sentence(lines, i):
    """La ligne précédant le titre de page est-elle une phrase inachevée ('so-', 'repeated three') ?
    Si oui, le texte continue le remède en cours : ce n'est pas un trou du scan."""
    for k in range(i - 1, max(0, i - 12), -1):
        prev = lines[k].strip()
        if sum(c.isalnum() for c in prev) >= 4:
            return not re.search(r"[.!?)\]]['\"\s]*$", prev)
    return False

LOST_RE = re.compile(r"^(?P<pre>[^()]{0,10})\((?P<name>[A-Z][^()]{2,40})\)\s*(?P<post>.*)$")

def lost_header(s):
    """En-tête perdu par l'OCR : 'V (Purple Fish.)' -> ('Purple Fish', '')."""
    m = LOST_RE.match(s.strip())
    if not m or sum(c.isalpha() for c in m.group("pre")) > 3:
        return None
    return m.group("name").strip(" .,"), m.group("post").strip()

# ------------------------------------------------------------
# 3. Parsing
# ------------------------------------------------------------
def build_page_map(lines):
    """Page de chaque ligne. Les numéros lus dans les titres courants sont rares et parfois faux :
    on garde la plus longue suite croissante cohérente avec l'avancée dans le texte
    (30 à 150 lignes par page), puis on interpole entre ces points d'ancrage (précision ~±1 page)."""
    cand = []
    for i, l in enumerate(lines):
        s = l.strip()
        if sum(c.isalpha() for c in s) >= 3 and upper_ratio(s) >= 0.5:
            n = page_number(s)
            if n and 1 <= n <= 1200:
                cand.append((i, n))
    if not cand:
        return [None] * len(lines)
    best, prev = [1] * len(cand), [-1] * len(cand)
    for b in range(len(cand)):
        ib, nb = cand[b]
        for a in range(max(0, b - 60), b):
            ia, na = cand[a]
            dn, di = nb - na, ib - ia
            if dn > 0 and di / 150 - 1 <= dn <= di / 30 + 2 and best[a] + 1 > best[b]:
                best[b], prev[b] = best[a] + 1, a
    k = max(range(len(cand)), key=best.__getitem__)
    anchors = []
    while k != -1:
        anchors.append(cand[k]); k = prev[k]
    anchors.reverse()
    pm = [None] * len(lines)
    i0, n0 = anchors[0]
    for i in range(0, i0):
        pm[i] = max(1, n0 - (i0 - i) // 75)
    for (ia, na), (ib, nb) in zip(anchors, anchors[1:]):
        for i in range(ia, ib):
            pm[i] = na + (i - ia) * (nb - na) // (ib - ia)
    il, nl = anchors[-1]
    for i in range(il, len(lines)):
        pm[i] = nl + (i - il) // 75
    print(f"Pagination : {len(anchors)} titres courants retenus sur {len(cand)} lus "
          f"(p. {anchors[0][1]} à {anchors[-1][1]})")
    return pm

# Intitulés de section trop abîmés pour la reconnaissance approchée (relevés à la main)
LINE_FIXES = [
    (r"^Heeu't\.\s*—", "Heart. —"),                      # Lycopodium
    (r"^M\.o\^B\.\\\\tx\^s\.\s*—", "Modalities. —"),     # Lycopodium : 'M.o^B.\\tx^s.—'
]

def parse_text(raw):
    lines = raw.splitlines()
    for k, l in enumerate(lines):
        for pat, rep in LINE_FIXES:
            if re.match(pat, l):
                lines[k] = re.sub(pat, rep, l)
    remedies, cur, cur_sec = [], None, None
    page = None
    page_map = build_page_map(lines)
    rescan = False                                      # pages déjà lues, rescannées en double
    def add(sec, txt):
        cur["sections"].setdefault(sec, []).append(txt)
        cur["log"].append((sec, txt))
        cur.setdefault("log_pages", []).append(page)
    def close():
        if cur:
            cur["page_end"] = page
            # remède créé par une règle de fin de remède mais resté vide : faux positif
            if cur.get("via") and not any(t.strip() for _, t in cur["log"]):
                return
            remedies.append(cur)
    i = 0
    while i < len(lines):
        line, s = lines[i], lines[i].strip()
        page = page_map[i]                              # page estimée (voir build_page_map)
        if cur and is_caps_line(s) and is_stop_header(s):
            break                                       # début du répertoire
        # Pages rescannées : titre courant d'une page ANTÉRIEURE qui nomme un remède déjà clos
        # (ex. '4o6 LYCOFODIUMi' au milieu de Lycopus, p. 407) -> texte en double, ignoré
        if cur and not rescan and is_caps_line(s) and page is not None:
            n = page_number_loose(s)
            prev_hit = [r for r in remedies[-3:] if same_remedy(s, r["header_raw"])]
            if n is not None and page - 4 <= n < page and not same_remedy(s, cur["header_raw"]) and prev_hit:
                # Pages hors ordre (ex. Lycopodium p. 406 scannée après le début de Lycopus) :
                # le passage est rendu au remède précédent, seulement pour les sections qu'il n'a pas
                rescan = True
                cur["rescan_from_line"] = i + 1
                rescan_target, rescan_known, rescan_sec = prev_hit[-1], set(prev_hit[-1]["sections"]), None
                i += 1
                continue
        if rescan and s and not is_caps_line(s) and len(s) >= 4:
            m_sec = match_section(line)
            if m_sec:
                rescan_sec, txt = m_sec
            else:
                txt = line
            if rescan_sec and rescan_sec not in rescan_known:
                rescan_target["sections"].setdefault(rescan_sec, []).append(txt)
                rescan_target["log"].append((rescan_sec, txt))
                rescan_target.setdefault("log_pages", []).append(page)
                rescan_target["rescan_added"] = rescan_target.get("rescan_added", 0) + 1
        # Fin d'un passage rescanné : le scan reprend au début du remède en cours, dont l'en-tête
        # abîmé n'est pas en majuscules ('LYCOPUS  vmGmicus.') -> on repart sur cette 2e copie
        if rescan and s and same_remedy(s, cur["header_raw"]) and page_number_loose(s) is None:
            jj = loose_header(lines, i)
            if jj is not None:
                rescan = False
                skipped = i - cur.pop("rescan_from_line")
                nxt = lines[jj].strip()
                cur = {"header_raw": s, "common_name": ocr_clean(nxt.strip("(){}[],.^ ")),
                       "sections": {"intro": []}, "running_headers": [], "log": [],
                       "page_start": page, "rescan_skipped": skipped}
                cur_sec = "intro"
                i = jj + 1
                continue
        if is_remedy_header(lines, i):
            if rescan:
                rescan = False
                cur["rescan_skipped"] = i - cur.pop("rescan_from_line")
                if same_remedy(lines[i], cur["header_raw"]):
                    # le scan reprend au début du remède en cours : la 1re copie partielle est abandonnée
                    cur = None
            close()
            j = next_nonempty(lines, i)
            paren = lines[j].strip()
            paren = paren[paren.find("(") if "(" in paren else paren.find("{"):]
            cur = {"header_raw": s,
                   "common_name": ocr_clean(paren.strip("(){},.")),
                   "sections": {"intro": []}, "running_headers": [], "log": [],
                   "page_start": page if (page is not None or remedies) else 1}
            cur_sec = "intro"
            i = j + 1
            continue
        if cur is None or not s or len(s) < 4 or rescan:
            i += 1
            continue
        end_ctx = cur is not None and cur_sec in ("dose", "relationship", "modalities")
        # Fin de remède + en-tête abîmé (casse mixte, nom commun sans parenthèse)
        jj = loose_header(lines, i) if end_ctx else None
        if jj is not None:
            close()
            nxt = lines[jj].strip()
            cur = {"header_raw": s, "common_name": ocr_clean(nxt.strip("(){}[],.^ ")), "via": "loose",
                   "sections": {"intro": []}, "running_headers": [], "log": [], "page_start": page}
            cur_sec = "intro"
            i = jj + 1
            continue
        # Fin de remède + titre courant d'une autre page sans le remède en cours :
        # le début du remède suivant manque dans le scan (ex. '674 ZINCUM MBTALLICUM.')
        if (end_ctx and is_caps_line(s) and page_number(s) and not same_remedy(s, cur["header_raw"])
                and not mid_sentence(lines, i)):
            close()
            name_part = re.sub(r"^\s*\d+\s+|\s+\d+\s*$", "", s).strip()
            cur = {"header_raw": f"[GAP] {name_part}", "common_name": "", "via": "gap",
                   "sections": {"intro": []}, "running_headers": [s], "log": [], "page_start": page}
            cur_sec = "intro"
            i += 1
            continue
        if is_caps_line(s):                             # en-tête de page / bruit
            cur["running_headers"].append(s)
            i += 1
            continue
        # Séparation forcée : remède dont l'en-tête et le nom commun sont illisibles
        s_norm = re.sub(r"\s+", " ", s)
        forced = next((f for f in FORCED_SPLITS if f[0] in s_norm), None) if cur and cur_sec == "dose" else None
        if forced:
            close()
            marker, name, common = forced
            cur = {"header_raw": f"[SPLIT] {name}", "common_name": common,
                   "sections": {"intro": []}, "running_headers": [], "log": [], "page_start": page}
            cur_sec = "intro"
            add("intro", s_norm[s_norm.index(marker):])
            i += 1
            continue
        # En-tête perdu par l'OCR : "(Nom commun.)" isolé juste après une Dose
        lost = lost_header(s) if cur_sec in ("dose", "relationship") and cur["sections"].get(cur_sec) else None
        if lost and cur_sec == "relationship":
            # après Relationship, une parenthèse peut être une simple citation ("(Dr. G. D. Hallet)") :
            # on n'ouvre un remède que si la première section qui suit est une section de symptômes
            nxt = None
            for k in range(i + 1, min(i + 40, len(lines))):
                m = match_section(lines[k])
                if m:
                    nxt = m[0]
                    break
            if nxt is None or nxt in ("dose", "relationship", "modalities"):
                lost = None
        if lost:
            close()
            common, rest = lost
            cur = {"header_raw": f"[LOST] {common}", "common_name": common,
                   "sections": {"intro": []}, "running_headers": [], "log": [],
                   "page_start": page}
            cur_sec = "intro"
            if rest:
                add("intro", rest)
            i += 1
            continue
        sec = match_section(line)
        if sec:
            cur_sec, rest = sec
            add(cur_sec, rest)
        else:
            add(cur_sec, line)
        i += 1
    close()

    # Sections rendues par un passage hors ordre : remises avant Modalities/Relationship/Dose
    for r in remedies:
        if r.get("rescan_added"):
            tail = ("modalities", "relationship", "dose")
            r["sections"] = {k: v for k, v in sorted(r["sections"].items(),
                                                     key=lambda kv: kv[0] in tail and tail.index(kv[0]) + 1 or 0)}

    # Dernier remède (Zingiber) : si le titre REPERTORY n'a pas été reconnu, le répertoire
    # s'est collé à lui. On coupe au premier motif "MOT—" du répertoire, ou après la Dose.
    last = remedies[-1] if remedies else None
    if last and last["log"]:
        cut_at, cut_pos = None, None
        for k, (sec, txt) in enumerate(last["log"]):
            m = REPERTORY_RE.search(txt)
            if m:
                cut_at, cut_pos = k, m.start()
                break
        idx = next((k for k, (sec, _) in enumerate(last["log"]) if sec == "dose"), None)
        if idx is not None:
            keep = idx + 1
            while (keep < len(last["log"]) and keep < idx + 3 and last["log"][keep][0] == "dose"
                   and not last["log"][keep - 1][1].rstrip().endswith(".")):
                keep += 1
            if cut_at is None or keep < cut_at:
                cut_at, cut_pos = keep, 0
        if cut_at is not None and cut_at < len(last["log"]):
            sec0, txt0 = last["log"][cut_at]
            tail = [(sec0, txt0[cut_pos:])] + last["log"][cut_at + 1:]
            head = last["log"][:cut_at] + ([(sec0, txt0[:cut_pos])] if txt0[:cut_pos].strip() else [])
            last["cut_chars"] = sum(len(t) for _, t in tail)
            last["cut_preview"] = " ".join(t.strip() for _, t in tail[:8])[:300]
            last["log"] = head
            if last.get("log_pages") and head:
                last["page_end"] = last["log_pages"][len(head) - 1]
            last["sections"] = {}
            for sec, txt in head:
                last["sections"].setdefault(sec, []).append(txt)

    out = []
    for r in remedies:
        suspicious = bool(re.search(r"[^A-Z\s\.\-]", r["header_raw"]))
        name = best_spelling(r["header_raw"], r["running_headers"]) if suspicious else clean_caps(r["header_raw"])
        secs = {k: join_lines(v) for k, v in r["sections"].items() if join_lines(v)}
        out.append({"remedy": name.title(), "header_raw": r["header_raw"],
                    "needs_review": suspicious, "common_name": r["common_name"],
                    "sections": secs, "page_start": r.get("page_start"),
                    "page_end": r.get("page_end"), "cut_chars": r.get("cut_chars", 0),
                    "cut_preview": r.get("cut_preview", "")})
    return out

def parse_modalities(t):
    worse, better = [], []
    parts = re.split(r"\b(worse|better)\b", t or "", flags=re.I)
    for k in range(1, len(parts) - 1, 2):
        items = [x.strip(" .;,") for x in re.split(r"[;,]", parts[k + 1]) if x.strip(" .;,")]
        (worse if parts[k].lower() == "worse" else better).extend(items)
    return worse, better

REL_KEYS = r"(Compare|Antidotes?|Complementary|Inimical)\s*:"

def parse_relationship(t):
    res = {}
    parts = re.split(REL_KEYS, t or "")
    for k in range(1, len(parts) - 1, 2):
        key = parts[k].lower().rstrip("s")
        body = re.sub(r"\([^)]*\)", "", parts[k + 1])
        items = [x.strip(" .,") for x in body.split(";") if x.strip(" .,")]
        res.setdefault(key, []).extend(items)
    return res

def build_tables(remedies):
    rows = []
    for r in remedies:
        r["worse"], r["better"] = parse_modalities(r["sections"].get("modalities"))
        r["relationship"] = parse_relationship(r["sections"].get("relationship", ""))
        for sec, txt in r["sections"].items():
            if sec in ("modalities", "relationship", "comparison", "dose"):
                continue
            protected = re.sub(r"\[[^\]]*\]",
                               lambda m: m.group(0).replace(";", "¦").replace(".", "·"), txt)
            for sent in re.split(r"(?<=[\.;])\s+(?=[A-Z])", protected):
                sent = sent.replace("¦", ";").replace("·", ".")
                refs = re.findall(r"\[([^\]]+)\]", sent)
                clean = re.sub(r"\[[^\]]*\]", "", sent).strip(" .;")
                if len(clean) > 3:
                    rows.append({"remedy": r["remedy"], "section": sec,
                                 "symptom": clean, "cross_refs": "; ".join(refs)})
    return pd.DataFrame(rows)

remedies = parse_text(raw)

# ------------------------------------------------------------
# 3b. Correction des noms et nettoyage
# ------------------------------------------------------------
OCR_RULES = [
    (r"\^", ""),
    (r"^l(?=[A-Z])", "I"),                 # lODATUM -> IODATUM
    (r"(?<=[A-Z])l(?=[A-Z])", "I"),        # MURlATICUM -> MURIATICUM
    (r"If(?=[A-Za-z])", "N"),              # IfATRUM -> NATRUM
    (r"(?:(?<=[A-Z])|^)m(?=[A-Z])", "IN"), # OFFICmALIS -> OFFICINALIS
    (r"tJ|TJ|tT|tr|tj", "U"),              # ALBtJS -> ALBUS
    (r"Xr", "TI"),                         # CAUSXrCUM -> CAUSTICUM
]

def apply_ocr_rules(tok):
    for pat, rep in OCR_RULES:
        tok = re.sub(pat, rep, tok)
    return re.sub(r"[^A-Za-z\-]", "", tok).upper()

def header_tokens(header):
    """Découpe l'en-tête, retire les débris OCR, recolle les finales séparées."""
    raw_toks = [t for t in re.split(r"[\s,\.;:—\[\]\(\)]+", header) if t]
    toks = []
    for t in raw_toks:
        letters = re.sub(r"[^A-Za-z]", "", t)
        if letters in ("A", "UM", "US", "AE") and t.isupper() and toks:  # "MURIATIC A"
            toks[-1] = toks[-1] + letters
            continue
        if len(letters) <= 2:                  # débris : "k", "I", "M", "{j", "_"
            continue
        toks.append(t)
    return toks

# Vocabulaire des lignes en MAJUSCULES (noms écrits en entier, sans abréviation)
caps_vocab = Counter(w for l in raw.splitlines() if is_caps_line(l.strip())
                       for w in re.findall(r"[A-Z]{4,}", clean_caps(l)))
caps_frequent = [w for w, n in caps_vocab.items() if n >= 3]

def fix_token(tok):
    """Retourne (mot corrigé, confirmé ?)."""
    plain = re.sub(r"[^A-Za-z\-]", "", tok).upper()
    if len(plain) < 4:                                        # NUX, LAC, FEL
        return plain, True
    if re.fullmatch(r"[A-Z\-]+", tok):                        # mot propre
        if caps_vocab[plain] >= 2:
            return plain, True
        near = [w for w in difflib.get_close_matches(plain, caps_frequent, n=5, cutoff=0.85)
                if len(w) == len(plain) and caps_vocab[w] >= max(3, 3 * caps_vocab[plain])]
        if near:
            return max(near, key=caps_vocab.get), True
        return plain, False
    ruled = apply_ocr_rules(tok)                              # mot abîmé
    for cand in (ruled, plain):
        if caps_vocab[cand] >= 2:
            return cand, True
    near = [w for w in difflib.get_close_matches(ruled, caps_frequent, n=5, cutoff=0.75)
            if abs(len(w) - len(ruled)) <= 1 and not ruled.startswith(w)]
    if near:
        return max(near, key=caps_vocab.get), True
    return ruled, False

def fix_name(header):
    toks = header_tokens(header)
    res = [fix_token(t) for t in toks]
    fixed = [w for w, _ in res]
    plain = [re.sub(r"[^A-Za-z\-]", "", t).upper() for t in toks]
    review = (fixed != plain
              or not all(ok for _, ok in res)
              or not all(re.fullmatch(r"[A-Z\-]+", t) for t in toks))
    return " ".join(fixed).title(), review

def clean_common(s):
    s = re.sub(r"(?:(?<=[a-z])O|\s+[0O])\s*$", "", s.strip())   # "TobaccoO", "Spider 0"
    s = re.sub(r"\s+[A-Z]{1,2}$", "", s)                          # "JH"
    s = re.sub(r"[\s\*\)\(/|'\.,;_]+$", "", s)
    return s.strip()

def norm_header(h):
    return re.sub(r"\s+", " ", h.strip())

GAP_FIX = {
    "[GAP] CHROM. ACID. CHRYSAROB. CICUTA": "Chromicum Acidum",
    "[GAP] ZINCUM MBTALLICUM.": "Zincum Metallicum",
    "[GAP] CANNABIS INDICA*": "Cannabis Indica",               # en-tête 'CANNABIS mDICA,' illisible
    "[GAP] TRITICUM TROMBIDIUM—TUBERCULINUM.": "Triticum",     # nom commun sans parenthèse
}

for r in remedies:
    if r["header_raw"].startswith("[GAP]"):
        key = norm_header(r["header_raw"])
        r["remedy"] = GAP_FIX.get(key, "? " + r["header_raw"][6:].title())
        r["needs_review"] = key not in GAP_FIX
        r["name_status"] = "en-tête absent ou illisible dans le scan (nommé d'après le titre de page)"
    elif r["header_raw"].startswith("[SPLIT]"):
        r["remedy"], r["needs_review"] = r["header_raw"][len("[SPLIT] "):], False
        r["name_status"] = "séparé manuellement (en-tête illisible)"
    elif not r["header_raw"].startswith("[LOST]"):
        r["remedy"], r["needs_review"] = fix_name(r["header_raw"])
        as_read = " ".join(re.sub(r"[^A-Za-z\-]", "", t).upper() for t in header_tokens(r["header_raw"])).title()
        r["name_status"] = "lu tel quel" if r["remedy"] == as_read else "corrigé automatiquement"
    r["common_name"] = clean_common(r["common_name"])

# --- Corrections manuelles, indexées sur l'en-tête OCR brut (espaces normalisés)
MANUAL_FIX = {
    'ABROTAHUM.': 'Abrotanum',
    'ACALYPHA UTDICA.': 'Acalypha Indica',
    'ACETIC ACm.': 'Acetic Acid',
    'ACTiEA SPICATA.': 'Actaea Spicata',
    'ADREITALm.': 'Adrenalin',
    'iSSSCULUS HIPPOCASTANUM.': 'Aesculus Hippocastanum',
    'MTBIOVS.': 'Aethiops',
    'iETHUSA CYNAPIUM.': 'Aethusa Cynapium',
    'AGRAPHIS KDTAITS.': 'Agraphis Nutans',
    'AILAHTHUS GLAITOULOSA.': 'Ailanthus Glandulosa',
    'ALUMEH.': 'Alumen',
    'AlfACARDIUM.': 'Anacardium',
    'AWANTHERUM.': 'Anantherum',
    'ANHALONHIM.': 'Anhalonium',
    'AHILIinJM.': 'Anilinum',
    'AHTHEMIS NOBILIS,': 'Anthemis Nobilis',
    'AURATUM.': 'Antimonium Sulphuratum Auratum',
    'AKTIPYRINE.': 'Antipyrine',
    'APIUM GRAVEOLEKS.': 'Apium Graveolens',
    'APOCYHUM AKBROS^MIFOLIUM.': 'Apocynum Androsaemifolium',
    'ARAKEA,': 'Aranea',
    'ARUICA.': 'Arnica',
    'ARSENICUM HYDROGErflSATUM.': 'Arsenicum Hydrogenisatum',
    'ARSENICUM lODATUM, {j': 'Arsenicum Iodatum',
    'ARSENICUM SULFURATUM FLAVTJM.': 'Arsenicum Sulphuratum Flavum',
    'ARUNDO IfAURITANICA.': 'Arundo Mauritanica',
    'ASIMIHA TMILOBA.': 'Asimina Triloba',
    'ASPARAGUS OFFICINALIS-': 'Asparagus Officinalis',
    'AURtTM MURIATICUM NATRON ATUM,': 'Aurum Muriaticum Natronatum',
    'BAPIAGA.': 'Badiaga',
    'BALSAMUM PERUVIAHUM,': 'Balsamum Peruvianum',
    'BARYTA lODATA.': 'Baryta Iodata',
    'BEIVZOICUM ACIDUM.': 'Benzoicum Acidum',
    'K BLATTA AMERICAITA.': 'Blatta Americana',
    'BOTHROPS LAJICIOLATUS.': 'Bothrops Lanceolatus',
    'BRAlfCA URSmA.': 'Branca Ursina',
    'CAJtrPUTUM (OLEUM WITTNEBIAKUM),': 'Cajuputum (Oleum Wittnebianum)',
    'CALCAREA lODATA.': 'Calcarea Iodata',
    'CAiraABIS SATIVA.': 'Cannabis Sativa',
    'CARBOHEUM OXYGENISATUM.': 'Carboneum Oxygenisatum',
    'CEAHOTHUS.': 'Ceanothus',
    'CEREUS BONPLAKDIL': 'Cereus Bonplandii',
    'CHELIDOISIDM MAJUS,': 'Chelidonium Majus',
    'CHEHOPODIUM AWTHELMIUTICUM.': 'Chenopodium Anthelminticum',
    'CHBTmUM ARSENICOSUM.': 'Chininum Arsenicosum',
    'CnfCHOITA OFFICmALIS,': 'Cinchona Officinalis',
    'CniNAMONUM.': 'Cinnamonum',
    'COCCUS CACTL': 'Coccus Cacti',
    'COLLmSpHIA CAJIABENSIS. M': 'Collinsonia Canadensis',
    'COMMOCLADD^L DENTATA.': 'Comocladia Dentata',
    'COM>URANGO.': 'Condurango',
    'COHVALLARIA MAJALIS.': 'Convallaria Majalis',
    'CORYDALIS, [DICEIfTRA CANADENSIS,]': 'Corydalis (Dicentra Canadensis)',
    '\\ CROCUS SAXrVA.': 'Crocus Sativus',
    'CUPRUM ARSENITUM.': 'Cuprum Arsenitum',
    'CYCLAMEW,': 'Cyclamen',
    'DOLICHOS PRURIEMS.': 'Dolichos Pruriens',
    'BORYPHORA.': 'Doryphora',
    'ELATERIUH.': 'Elaterium',
    'EQinSETUM,': 'Equisetum',
    'EUPATORIUM AROHATICUM.': 'Eupatorium Aromaticum',
    'EUPHORBItJlT.': 'Euphorbium',
    'FERRUM lODATTJM.': 'Ferrum Iodatum',
    'FRAJJCISCEA.': 'Franciscea',
    'FRAXIKUS AHERICAHA.': 'Fraxinus Americana',
    'kGAMBOGU.': 'Gambogia',
    'GIN SENG.': 'Ginseng',
    'GLOHOmE.': 'Glonoine',
    'GOLONDRIHA.': 'Golondrina',
    '|k GRAHATUM.': 'Granatum',
    'GUACO-': 'Guaco',
    'GYMHOCLADUS.': 'Gymnocladus',
    'ITELIAWTHUS.': 'Helianthus',
    'HELQDERMA,': 'Heloderma',
    'HELOlfUS.': 'Helonias',
    'HIPPOZ^NIIfUM.': 'Hippozaeninum',
    'HTDROPHOBmUM.': 'Hydrophobinum',
    'HYPERICXm.': 'Hypericum',
    'mBIGO,': 'Indigo',
    'lODUM. I': 'Iodum',
    'JACARANBA.': 'Jacaranda',
    'JEQUmiTY.': 'Jequirity',
    'JUGLANS CIWEREA.': 'Juglans Cinerea',
    'JUHIPERUS.': 'Juniperus',
    'KALI ARSEHICUM.': 'Kali Arsenicosum',
    'KALI CARBOWICUM.': 'Kali Carbonicum',
    'KALI CYAlfATUM,': 'Kali Cyanatum',
    'KALI NITRICDM— NITRUM,': 'Kali Nitricum (Nitrum)',
    'KALI PERMATrGANICUM.': 'Kali Permanganicum',
    'KKEOSOTVU.': 'Kreosotum',
    'LABURHUM,': 'Laburnum',
    'LAC CANmUM.': 'Lac Caninum',
    'LACHESlS.': 'Lachesis',
    'I LACTICUM ACIBUM, M': 'Lacticum Acidum',
    'LAPIS ALBtJS.': 'Lapis Albus',
    'LILIUM TIGRIRUM.': 'Lilium Tigrinum',
    'LIMDLUS. [XIPHOSURA.]': 'Limulus (Xiphosura)',
    'LDTARIA.': 'Linaria',
    'MAGNESIA MTTRIATICA.': 'Magnesia Muriatica',
    'MAGWOLIA GRAimiFLORA.': 'Magnolia Grandiflora',
    'MEDOMRHINUM.': 'Medorrhinum',
    'MEKISPERMUM.': 'Menispermum',
    'HEUTHA PIPERITA.': 'Mentha Piperita',
    'MERCtJRmS CORROgiVUS.': 'Mercurius Corrosivus',
    'MlRCUItlUS lODATUS FLAVUS.': 'Mercurius Iodatus Flavus',
    'MERCURIDS lODATUS RUBER.': 'Mercurius Iodatus Ruber',
    'MERCUHIUS SULPHURICUS.': 'Mercurius Sulphuricus',
    'HAJA TRIPUDlAlfS.': 'Naja Tripudians',
    'NATRUM CARBOHICUM.': 'Natrum Carbonicum',
    'HATRUM PHOSPHORICUM.': 'Natrum Phosphoricum',
    'MATRUM SULPHURICUM,': 'Natrum Sulphuricum',
    'HEGUKDO.': 'Negundo',
    'IflCCOLUM.': 'Niccolum',
    'IflTRO-MURlATIC ACm,': 'Nitro-Muriatic Acid',
    'OCIM. CAN. — ^mNANTHE,': 'Oenanthe Crocata',
    'OWISCUS ASELLUS— MILLEPEDES,': 'Oniscus Asellus (Millepedes)',
    'rOOPHORINUM.': 'Oophorinum',
    'OPUKTIA VULGARIS.': 'Opuntia Vulgaris',
    'OVI GALLISJE PELLICULA.': 'Ovi Gallinae Pellicula',
    'IPARAFFIITE.': 'Paraffine',
    'PEBICULUS.': 'Pediculus',
    'PEHTHORUM,': 'Penthorum',
    'PETROSELIWUM.': 'Petroselinum',
    'PHYSOSTIGBIA.': 'Physostigma',
    'FINDS SYLVESTRIS.': 'Pinus Sylvestris',
    'PIPIR METHYSTICUM. V': 'Piper Methysticum',
    'PLAMTAGO MAJOR.': 'Plantago Major',
    'PLATIHA.': 'Platina',
    'POPULUS CAHDICAHS,': 'Populus Candicans',
    'POPULUS TREMULQIDES.': 'Populus Tremuloides',
    'POTHOS FCETIDUS.': 'Pothos Foetidus',
    'PROPYL AMIN.': 'Propylamin',
    'PSOHIHUM.': 'Psorinum',
    'PULEX IRRITAIIS.': 'Pulex Irritans',
    'QUERCUS GLMfDIUM SPIRITUS.': 'Quercus Glandium Spiritus',
    'RATAKHU.': 'Ratanhia',
    'RUMEX CRISPtrS.': 'Rumex Crispus',
    'SACCHARUM OFFICOALE,': 'Saccharum Officinale',
    'SANGUIS ARIA.': 'Sanguinaria',
    'SAJfGUINARmA NITRICA.': 'Sanguinarina Nitrica',
    'SAMICULA.': 'Sanicula',
    'SAITTONnrUM.': 'Santoninum',
    'SARRACEITIA PURPtTREA.': 'Sarracenia Purpurea',
    'SCUTELLARIA LATERIFOLU,': 'Scutellaria Lateriflora',
    'SEDTTM ACRE.': 'Sedum Acre',
    'SALAGmELLA APUS.': 'Selaginella Apus',
    'SELEWIUM,': 'Selenium',
    'SOLARUM JTIGRUM.': 'Solanum Nigrum',
    'SOLDDAGO VERGA.': 'Solidago Virga',
    'SPIR^A ULMARIA.': 'Spiraea Ulmaria',
    'SPIRAHTHES,': 'Spiranthes',
    'STELLARU MEDIA.': 'Stellaria Media',
    'STERCUCIA,': 'Sterculia',
    'SULFOKAL,': 'Sulfonal',
    'SYZYGIUM JAMBOLAHUM.': 'Syzygium Jambolanum',
    'TARAITTULA CUBENSIS.': 'Tarantula Cubensis',
    'TARANTULA HISPAHIA,': 'Tarantula Hispania',
    'TEREBINTHIHA.': 'Terebinthina',
    'TEUCRIUM MARLM:': 'Teucrium Marum',
    'THIOSlNAMIirUM.': 'Thiosinaminum',
    'TILIA EUROPjEA,': 'Tilia Europaea',
    'TITAWIUM.': 'Titanium',
    'TROMBIBUJM,': 'Trombidium',
    'TURHERA.': 'Turnera',
    'UREJl.': 'Urea',
    'tVERBEHA, (': 'Verbena',
    'VISCDM ALBUM,': 'Viscum Album',
    'tXANTHOXYLUM,': 'Xanthoxylum',
    ".' ZmClTM VALERIANUM,": 'Zincum Valerianicum',
    # --- revue n°10 (en-têtes détectés après correction des règles, texte réel)
    'AMMONIUM   BENZ0ICX3M.': 'Ammonium Benzoicum',
    'AMM05IUM    CAUSTICUM.': 'Ammonium Causticum',
    '^H  AMYGDALUS    PERSICA,': 'Amygdalus Persica',
    '^H  ANAGALLIS.': 'Anagallis',
    '^B  ASAFCETIDA.': 'Asafoetida',
    'BELLIS    PERENI7I5.': 'Bellis Perennis',
    '»  BLATTA    ORIENTALIS,': 'Blatta Orientalis',
    'B0R4X,': 'Borax',
    'I  BORICUM     ACIDUM,': 'Boricum Acidum',
    'l^  BROMTOM.  *  V': 'Bromium',
    '^^r  CACTUS     GRAKDJFLORUS.': 'Cactus Grandiflorus',
    '^^,  CADinUM    SULPH.': 'Cadmium Sulphuratum',
    '^B  CHEKOPODO     GLAUCI     APHIS.': 'Chenopodii Glauci Aphis',
    '^         COCCmELLA     SEPTEMPUnCTATA,': 'Coccinella Septempunctata',
    'COCC0LUS,': 'Cocculus',
    'DUBOISIA.': 'Duboisia',
    '^^  EPIGEA.': 'Epigea',
    '^B  EUPATORIUM    PURPUREUM.  ^': 'Eupatorium Purpureum',
    '^-  EUPHORBIA    LATHYRIS,  ■': 'Euphorbia Lathyris',
    'FAGOPYR0M,': 'Fagopyrum',
    'FUCUS    VESICULOSUS.': 'Fucus Vesiculosus',
    '^^^^.  HYBROCYANIC    ACm.': 'Hydrocyanic Acid',
    'LATRODECT0S,': 'Latrodectus Mactans',
    '^^^^     LOBELIA     PURPURESCENS.': 'Lobelia Purpurascens',
    '^L  MALAIfDRmUM.': 'Malandrinum',
    'I  MERCURIUS    CYAHATUS.': 'Mercurius Cyanatus',
    '^^^^  OLEUM    ANIMALE.': 'Oleum Animale',
    'PARIS    Q0ADRTFOLIA.': 'Paris Quadrifolia',
    'Hf  FIX    LIQUIDA.  M': 'Pix Liquida',
    'H  PLUMBDM    lODATUM.  ^^^1': 'Plumbum Iodatum',
    'SCROPHULAltlA     NODOSA.': 'Scrophularia Nodosa',
    'j^-^  SILPHIUM.': 'Silphium Laciniatum',
    '^^  SULPHUR    lODATUM.': 'Sulphur Iodatum',
    'THLASPI   BUBSA  PAST0RI8.': 'Thlaspi Bursa Pastoris',
    'VARIOLmUM.': 'Variolinum',
    '^^^B  VBRATRUM    VIRIDE.': 'Veratrum Viride',
    # --- revue n°11 (contrôlés sur le texte OCR brut)
    'ANTiMorrnjM    chloridum.': 'Antimonium Chloridum',
    'AKTIMONIUM    SULPHURATUM': 'Antimonium Sulphuratum Auratum',
    'cmEX.': 'Cimex',
    'coimus  CmCINATA.': 'Cornus Circinata',
    'ERioDicxyoir.': 'Eriodictyon',
    'affiMATOXYLON.': 'Haematoxylon',
    'IRIDnjM.': 'Iridium',
    'CJUNCUS    EFFDSUS.': 'Juncus Effusus',
    'LYCOPUS    VIRGIWICUS,': 'Lycopus Virginicus',
    'LYCOPUS  vmGmicus.': 'Lycopus Virginicus',
    'MEDOHRmNUM.': 'Medorrhinum',
    'METHYLEITE    BLUE,': 'Methylene Blue',
    'I  PRUNUS    SPIlfOSA.': 'Prunus Spinosa',
    'moBmiA,': 'Robinia',
    'SABINA,': 'Sabina',
    'SANICULA.': 'Sanicula',
    'STANNCM.': 'Stannum',
}

# Noms communs illisibles ou décalés par l'OCR (contrôlés sur le texte brut)
COMMON_FIX = {
    "Antimonium Chloridum": "Butter of Antimony",
    "Antimonium Sulphuratum Auratum": "Golden Sulphuret of Antimony",
    "Cannabis Indica": "Hashish",
    "Cornus Circinata": "Round-leaved Dogwood",
    "Eriodictyon": "Yerba Santa",
    "Iridium": "The metal",
    "Juncus Effusus": "Common Rush",
    "Lycopus Virginicus": "Bugle-Weed",
    "Medorrhinum": "The Gonorrhoeal Virus",
    "Methylene Blue": "One of the Aniline Dyes",
    "Prunus Spinosa": "Black-Thorn",
    "Sabina": "Savine",
    "Sanicula": "The Water of Sanicula Springs, Ottawa, Ill.",
    "Stannum": "Tin",
    "Triticum": "Couch-grass",
    "Zingiber": "Ginger",
    "Spongia Tosta": "Roasted Sponge",
}

def norm_header(h):
    return re.sub(r"\s+", " ", h.strip())

MANUAL_FIX = {norm_header(k): v for k, v in MANUAL_FIX.items()}   # clés insensibles aux espaces OCR
n_fixed = 0
for r in remedies:
    key = norm_header(r["header_raw"])
    if key in MANUAL_FIX:
        r["remedy"], r["needs_review"] = MANUAL_FIX[key], False
        r["name_status"] = "corrigé manuellement"
        n_fixed += 1
print(f"Corrections manuelles appliquées : {n_fixed} / {len(MANUAL_FIX)}")
for r in remedies:
    if r["remedy"] in COMMON_FIX:
        r["common_name"] = COMMON_FIX[r["remedy"]]

# --- Noms validés après revue (corrects mais non confirmables automatiquement)
VALIDATED = {
    "Agave Americana", "Agnus Castus", "Ambrosia", "Ammonium Picratum",
    "Apocynum Cannabinum", "Arbutus Andrachne", "Asarum", "Asclepias Syriaca",
    "Azadirachta Indica", "Baryta Muriatica", "Benzinum", "Bismuthum",
    "Boletus Laricis", "Brachyglottis", "Calcarea Arsenica", "Calcarea Renalis",
    "Caltha Palustris", "Camphora Mono-Bromata", "Canchalagua", "Carbo Vegetabilis",
    "Carbolicum Acidum", "Carboneum Sulphuratum", "Cascarilla", "Castanea Vesca",
    "Castoreum", "Caulophyllum", "Chimaphila Umbellata", "Chrysarobinum",
    "Clematis Erecta", "Dioscorea Villosa", "Diphtherinum", "Drosera",
    "Elaps Corallinus", "Erechtites", "Erigeron", "Euonymus Atropurpureus",
    "Fragaria", "Galium Aparine", "Gallicum Acidum", "Geranium Maculatum",
    "Gnaphalium", "Gratiola", "Grindelia", "Guaiacum", "Hydrangea", "Hydrocotyle",
    "Illicium", "Iodoformum", "Kali Chloricum", "Lac Defloratum", "Lachnantes",
    "Lobelia Inflata", "Lolium Temulentum", "Lonicera", "Melilotus", "Menyanthes",
    "Mezereum", "Millefolium", "Mygale", "Naphthaline", "Ocimum Canum",
    "Onosmodium", "Oreodaphne", "Origanum", "Passiflora Incarnata",
    "Paullinia Sorbilis", "Phaseolus", "Phellandrium", "Polygonum Punctatum",
    "Primula Veris", "Quillaya Saponaria", "Ranunculus Sceleratus", "Rhododendron",
    "Rhus Aromatica", "Rhus Glabra", "Rhus Venenata", "Rosa Damascena",
    "Ruta Graveolens", "Sambucus Nigra", "Sempervivum Tectorum", "Skookum-Chuck",
    "Solanum Lycopersicum", "Spartium Scoparium Scoparius", "Staphisagria",
    "Stigmata Maydis", "Stillingia", "Strophantus Hispidus", "Symphoricarpus",
    "Symphytum", "Tanacetum Vulgare", "Taraxacum", "Taxus Baccata",
    "Thaspium Aureum Zizia", "Trillium Pendulum", "Triosteum Perfoliatum",
    "Tussilago Petasites", "Usnea Barbata", "Ustilago Maydis", "Verbascum",
}
for r in remedies:
    if r["remedy"] in VALIDATED:
        r["needs_review"] = False
        r["name_status"] = "validé manuellement"

# --- Noms corrects validés lors de la revue n°7
VALIDATED_2 = {
    "Abies Canadensis", "Asclepias Tuberosa", "Cahinca", "Calcarea Sulphurica",
    "Causticum", "Coffea Cruda", "Coto", "Crataegus", "Ferrum Picricum", "Guarea",
    "Hedeoma", "Hekla Lava", "Helleborus", "Hippomanes", "Homarus", "Hydrastis",
    "Iberis", "Ipecacuanha", "Iris Versicolor", "Magnesia Phosphorica",
    "Malaria Officinalis", "Mancinella", "Mimosa", "Mitchella", "Natrum Muriaticum",
    "Natrum Salicylicum", "Salicylicum Acidum", "Salix Nigra", "Salvia Officinalis",
    "Sticta", "Strontia", "Sulphuricum Acidum", "Thallium", "Thuja", "Tongo",
    "Trifolium Pratense",
}
for r in remedies:
    if r["remedy"] in VALIDATED_2:
        r["needs_review"] = False
        r["name_status"] = "validé manuellement"

# --- En-têtes perdus par l'OCR, renommés via leur nom commun (espaces normalisés)
LOST_FIX = {
    "Hydrate of Ammonia": "Ammonium Causticum",
    "Peach Bark": "Amygdalus Persica",
    "Indian Cockroach": "Blatta Orientalis",
    "Boracic Acid": "Boricum Acidum",
    "Borate of Soditun": "Borax",
    "Cadmic Sulphate": "Cadmium Sulphuratum",
    "Spanish Fly": "Cantharis",
    "Goat-bufih": "Chaparro Amargoso",
    "PlMnt'IAct from CbenopcNUuin": "Chenopodii Glauci Aphis",
    "Bedhug": "Cimex Lectularius",
    "Worm-Seed": "Cina",
    "Round^&aved Dagwood": "Cornus Circinata",
    "Corkwood Tree": "Duboisia",
    "Button Snake- Root": "Eryngium Aquaticum",
    "Thorough wort": "Eupatorium Perfoliatum",
    "Queen o| ttie Meadow": "Eupatorium Purpureum",
    "Gopher-Plant": "Euphorbia Lathyris",
    "Buckwheat": "Fagopyrum",
    "MAle Fern": "Filix Mas",
    "Sea Kelp": "Fucus Vesiculosus",
    "Wahiut": "Juglans Regia",
    "Common Rush": "Juncus Effusus",
    "Spider": "Latrodectus Mactans",
    "Purple Lobelia": "Lobelia Purpurascens",
    "Cyanide of Mercury": "Mercurius Cyanatus",
    "Purple Fish": "Murex",
    "Myrtle": "Myrtus Communis",
    "Peony": "Paeonia",
    "Fabiana": "Pichi",
    "Pme-Tar": "Pix Liquida",
    "Iodide of Lead": "Plumbum Iodatum",
    "Black-Thorn": "Prunus Spinosa",
    "Buttercup": "Ranunculus Bulbosus",
    "Knotted Figwort": "Scrophularia Nodosa",
    "Snake wort": "Senega",
    "Rosm-Weed": "Silphium Laciniatum",
    "Tin": "Stannum",
    "Iodide of Sulphur": "Sulphur Iodatum",
    "Lymph from Smallpox Pustule": "Variolinum",
    "Rattlesnake Bean": "Cedron",
    "Logwood": "Haematoxylon",
    "Bugle-Weed": "Lycopus Virginicus",
    "Quassia -Wood": "Quassia",
    "Yellow Locust": "Robinia",
}
lost = [r for r in remedies if r["header_raw"].startswith("[LOST]")]
print(f"En-têtes perdus récupérés : {len(lost)}")
for r in lost:
    key = re.sub(r"\s+", " ", r["common_name"]).strip()
    r["common_name"] = key
    name = LOST_FIX.get(key)
    r["remedy"], r["needs_review"] = (name, False) if name else (f"? ({key})", True)
    r["name_status"] = "récupéré via le nom commun"
    print(f"  {key!r:35} -> {r['remedy']}  ({len(r['sections'])} sections)")

# --- Faux Moschus = fin de Morphinum numérisée deux fois
#     (identifié par ses sections, toutes présentes dans Morphinum)
morph = next((r for r in remedies if r["remedy"] == "Morphinum"), None)
mos = [r for r in remedies if r["remedy"] == "Moschus"]
fake = [m for m in mos if morph and len(mos) > 1
        and set(m["sections"]) - {"intro"} <= set(morph["sections"])]
for f in fake:
    print(f"Faux Moschus supprimé : {len(f['sections']) - 1} sections, toutes présentes dans Morphinum")
remedies = [r for r in remedies if all(r is not f for f in fake)]

# --- Contrôle des doublons restants (signalés, jamais supprimés automatiquement)
dup = Counter(r["remedy"] for r in remedies)
for r in remedies:
    if dup[r["remedy"]] > 1:
        r["needs_review"] = True
print("Doublons restants :", {k: v for k, v in dup.items() if v > 1} or "aucun")
print(f"Remèdes : {len(remedies)}")

# --- Corrections OCR manuelles, phrase par phrase, relues sur le scan
#     (remède, section, texte OCR tel qu'il est dans le JSON, texte corrigé)
OCR_FIXES = [
    ("Hepar Sulphuris", "abdomen",
     "Stitching in region of liver when walkingi coughing, breathifigj or touching it. [Bry.; Merc]",
     "Stitching in region of liver when walking, coughing, breathing, or touching it. [Bry.; Merc.]"),
]
# Corrections saisies dans la feuille boericke_a_corriger.csv (colonne texte_corrige remplie), si elle est fournie
FIX_CSV = "boericke_a_corriger.csv"
if os.path.exists(FIX_CSV):
    _fx = pd.read_csv(FIX_CSV, dtype=str, keep_default_na=False)
    for col in ("proposition_ia", "valider"):
        if col not in _fx.columns:
            _fx[col] = ""
    # priorité à ta propre correction ; sinon proposition IA marquée « o » dans la colonne valider
    _ok = _fx["valider"].str.strip().str.lower().isin(["o", "oui", "x", "1", "y", "yes"])
    _n_main = _n_ia = 0
    for _i, row in _fx.iterrows():
        if row["texte_corrige"].strip():
            OCR_FIXES.append((row["remedy"], row["section"], row["texte_ocr"], row["texte_corrige"].strip(), "manuelle"))
            _n_main += 1
        elif _ok[_i] and row["proposition_ia"].strip():
            OCR_FIXES.append((row["remedy"], row["section"], row["texte_ocr"], row["proposition_ia"].strip(),
                              "validée : " + (row.get("source_proposition", "").strip() or "proposition IA")))
            _n_ia += 1
    print(f"Feuille de corrections lue : {_n_main} correction(s) manuelle(s), {_n_ia} proposition(s) IA validée(s)")
n_ocr_fix = 0
for fx in OCR_FIXES:
    name, sec, old, new = fx[:4]
    origin = fx[4] if len(fx) > 4 else "manuelle"
    r = next((x for x in remedies if x["remedy"] == name), None)
    txt = r["sections"].get(sec, "") if r else ""
    if old in txt:
        r["sections"][sec] = txt.replace(old, new, 1)
        r.setdefault("corrections_ocr", []).append({"section": sec, "avant": old, "apres": new, "origine": origin})
        n_ocr_fix += 1
    elif not (r and new in txt):
        print(f"  Correction OCR introuvable : {name} / {sec} : {old[:60]}…")
print(f"Corrections OCR manuelles appliquées : {n_ocr_fix} / {len(OCR_FIXES)}")

# --- Posologies hors section Dose : retirées du texte affiché et indexé
#     (Dose illisible noyée dans Relationship, usages non homéopathiques, mentions de grains, gouttes, teintures…)
#     Le texte retiré est conservé dans r["posologie_hors_dose"] pour traçabilité, jamais affiché par l'app.
_NUM = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen|twenty|thirty|half)"
POSO_RE = re.compile("|".join([
    r"(?<!im)(?<!im\s)\bpotenc(?:y|ies)\b", r"\btritur", r"\btrit\b", r"\battenuation", r"\bdilution",
    r"\btincture\b", r"\bgrains?\b", r"\bgr\.\s", r"\bminims?\b", r"\bgrammes?\b", r"\bgtt\b",
    r"\b(?:tea|table|dessert)[\s-]?spoonful", r"\bhypoderm", r"\binject(?:ed|ions?)\s+(?:under|into|of)\b",
    r"\bper[\s-]+cent\b", r"[1-9]\s?%", r"\bc\.\s?c\.", r"\b[1-9]\d{0,2}\s?[xX]\b", r"\b(?:3|6|12|30|200)c\b",
    _NUM + r"[\s-]drops?\b", r"\bdrop[\s-]doses?\b", r"(?<!large\s)(?<!smaller\s)(?<!toxic\s)\bdoses?\b",
    r"\btimes\s+(?:a|per)\s+day\b", r"\bevery\s+" + _NUM + r"\s+(?:hours|minutes)\b",
    r"\b(?:ointment|cerate|lotion|liniment|suppositor\w*|gargle|douche|infusion|decoction)s?\b",
    r"\bspray\b", r"\binhalation\b", r"\blocally\b(?!,?\s+it\s+has)", r"\b(?:used|employed|given)\s+externally\b",
    r"\bexternally\s+(?:in|for|as)\b", r"\boz\.", r"\bounces?\b", r"\bdrams?\b",
    r"homoeopathic\s+(?:uses|preparations)", r"\bnon-?\s?homoeopathic\b", r"\bphysiological\s+(?:doses?|effects?)",
]), re.I)
# Intitulé "Dose" défiguré par l'OCR ('I>ose, —', 'IkQWi, — Tine tare', 'Bo&e, —') ou usages non homéopathiques :
# tout ce qui suit dans la section appartient à la posologie
DOSE_START = re.compile(
    r"^.{0,14}?[—–]\s*.{0,25}\b(?:potenc\w*|tritur\w*|tinct\w*|tine|attenu\w*|dilut\w*|drops?|grains?|doses?|"
    r"lower|higher|first|third|sixth|twelfth|thirtieth)\b"
    r"|^\W*(?:Dose|Extra[\s-]*Hom\w*opathic|Non[\s-]*Hom\w*opathic)\b|(?:Non|Extra)[\s-]*Hom\w*opathic\s+(?:Uses|Preparations)",
    re.I)
TAIL_SECS = {"relationship", "comparison", "modalities"}

def split_keep(txt):
    """Découpe en phrases sans rien retirer (les renvois [Acon.] restent dans le texte)."""
    protected = re.sub(r"\[[^\]]*\]", lambda m: m.group(0).replace(";", "¦").replace(".", "·"), txt)
    return [x.replace("¦", ";").replace("·", ".") for x in re.split(r"(?<=[\.;])\s+(?=[A-Z])", protected) if x.strip()]

n_poso = Counter()
for r in remedies:
    removed = {}
    secs = [k for k in r["sections"] if k not in ("dose", "extra homoeopathic uses")]
    for sec in secs:
        kept, tail = [], False
        tail_ok = sec in TAIL_SECS or sec == secs[-1]
        for snt in split_keep(r["sections"][sec]):
            if tail or (tail_ok and DOSE_START.search(snt)):
                tail = True
                removed.setdefault(sec, []).append(snt)
                continue
            if not POSO_RE.search(snt):
                kept.append(snt)
                continue
            if sec in TAIL_SECS:
                # liste de comparaisons : seule la sous-partie (entre « ; ») est masquée, sur place
                out = []
                for part in re.split(r"(?<=;)\s+", snt):
                    if not POSO_RE.search(part):
                        out.append(part)
                        continue
                    removed.setdefault(sec, []).append(part)
                    opened = part.count("(") - part.count(")")
                    out.append(("(" if opened > 0 else "") + "[posologie masquée]"
                               + (")" * -opened if opened < 0 else "") + (";" if part.rstrip().endswith(";") else ""))
                kept.append(re.sub(r"(\[posologie masquée\];?\s*){2,}", "[posologie masquée] ", " ".join(out)))
            else:
                removed.setdefault(sec, []).append(snt)
        new = " ".join(kept).strip()
        if new:
            r["sections"][sec] = new
        else:
            del r["sections"][sec]
    if removed:
        r["posologie_hors_dose"] = removed
        n_poso[r["remedy"]] = sum(len(v) for v in removed.values())
print(f"Posologies hors Dose retirées : {sum(n_poso.values())} passage(s) dans {len(n_poso)} remède(s)")
for name in ("Mercurius Corrosivus", "Sulfonal", "Plumbum Metallicum", "Zincum Metallicum"):
    rr = next((x for x in remedies if x["remedy"] == name), None)
    if rr:
        print(f"  {name:22} -> {rr.get('posologie_hors_dose', {})}"[:300])

sym = build_tables(remedies)   # reconstruit la table avec les noms corrigés
assert isinstance(sym, pd.DataFrame), "build_tables n'a rien renvoyé"
print(f"Table symptômes : {len(sym):,} lignes")

# ------------------------------------------------------------
# 3c. Qualité OCR par phrase, référence source, validation
# ------------------------------------------------------------
import subprocess, sys
from urllib.parse import quote
try:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "wordfreq"], check=False)
    from wordfreq import zipf_frequency
except Exception:
    zipf_frequency = None
    print("wordfreq indisponible : qualité OCR estimée sur le seul vocabulaire du livre")

book_vocab = Counter(w.lower() for w in re.findall(r"[A-Za-z]{3,}", raw))

def word_ok(w):
    lw = w.lower()
    if book_vocab[lw] >= 3:                       # les fautes OCR sont rarement répétées
        return True
    return zipf_frequency is not None and zipf_frequency(lw, "en") >= 2.0

def ocr_quality(text):
    words = re.findall(r"[A-Za-z]{3,}", text)
    if not words:
        return 0.5
    ok = sum(word_ok(w) for w in words) / len(words)
    junk = len(re.findall(r"[^A-Za-z0-9\s\.,;:\-'\"()\[\]!?&/]", text))
    return round(max(0.0, ok - min(0.3, 0.05 * junk)), 2)

def ocr_level(q):
    return "fiable" if q >= 0.9 else ("à vérifier" if q >= 0.75 else "douteux")

def split_sentences(txt):
    out = []
    protected = re.sub(r"\[[^\]]*\]", lambda m: m.group(0).replace(";", "¦").replace(".", "·"), txt)
    for s in re.split(r"(?<=[\.;])\s+(?=[A-Z])", protected):
        s = re.sub(r"\[[^\]]*\]", "", s.replace("¦", ";").replace("·", ".")).strip(" ;")
        if len(s) > 3:
            out.append(s)
    return out

REVIEW_OCR_MIN = 0.90            # sous ce score OCR moyen, la fiche est marquée needs_review
LINE_SKIP = {"dose", "extra homoeopathic uses", "relationship", "modalities"}
for r in remedies:
    r["lines"] = {sec: [[s, ocr_quality(s)] for s in split_sentences(txt)]
                  for sec, txt in r["sections"].items() if sec not in LINE_SKIP}
    qs = [q for pairs in r["lines"].values() for _, q in pairs]
    r["ocr"] = {
        "score": round(sum(qs) / len(qs), 2) if qs else None,
        "fiable": sum(q >= 0.9 for q in qs),
        "a_verifier": sum(0.75 <= q < 0.9 for q in qs),
        "douteux": sum(q < 0.75 for q in qs),
    }
    # needs_review = la fiche demande une relecture humaine, pour l'une ou l'autre raison
    r["name_review"] = bool(r["needs_review"])
    reasons = []
    if r["name_review"]:
        reasons.append("nom incertain")
    if r["ocr"]["score"] is not None and r["ocr"]["score"] < REVIEW_OCR_MIN:
        reasons.append(f"OCR {r['ocr']['score']:.2f} < {REVIEW_OCR_MIN:.2f}")
    if r.get("posologie_hors_dose"):
        reasons.append("posologie retirée hors section Dose")
    r["review_reasons"] = reasons
    r["needs_review"] = bool([x for x in reasons if not x.startswith("posologie")])
    token = (clean_caps(r["header_raw"].replace("[LOST]", "")).split() or [""])[0]
    if r["header_raw"].startswith("[LOST]"):
        token = r["common_name"].split()[0] if r["common_name"] else ""
    pages = (f"p. {r['page_start']}" if r.get("page_start") else "page inconnue") + \
            (f"–{r['page_end']}" if r.get("page_end") and r.get("page_start") and r["page_end"] > r["page_start"] else "")
    r["source_ref"] = {
        "ouvrage": "Boericke, Pocket Manual of Homoeopathic Materia Medica, 3e éd., 1906",
        "pages": pages,
        "page_start": r.get("page_start"),
        "page_end": r.get("page_end"),
        "entete_ocr": r["header_raw"],
        "url": f"https://archive.org/details/{SRC_ID}?q={quote(token)}",
    }

# Feuille de correction : phrases OCR < 0.90, des fiches les plus abîmées aux moins abîmées.
# Remplir texte_corrige (en relisant le scan), puis la fournir avec le script au prochain lancement.
fix_rows = []
for r in sorted(remedies, key=lambda x: (x["ocr"]["score"] is None, x["ocr"]["score"] or 0)):
    done = {c["apres"] for c in r.get("corrections_ocr", [])}
    for sec, txt in r["sections"].items():
        if sec in ("dose", "extra homoeopathic uses"):
            continue
        for snt in split_keep(txt):
            q = ocr_quality(re.sub(r"\[[^\]]*\]", "", snt))
            if q < 0.9 and snt not in done:
                fix_rows.append({"remedy": r["remedy"], "score_fiche": r["ocr"]["score"], "section": sec,
                                 "score_phrase": q, "pages": r["source_ref"]["pages"], "scan": r["source_ref"]["url"],
                                 "texte_ocr": snt, "texte_corrige": ""})
a_corriger = pd.DataFrame(fix_rows)
print(f"Feuille de correction : {len(a_corriger):,} phrase(s) OCR < 0.90 dans {a_corriger['remedy'].nunique() if len(a_corriger) else 0} remède(s)")

# Ordre habituel des sections dans Boericke : un retour en arrière après la fin d'un remède
# (Relationship, Dose, Modalities) signale presque toujours un en-tête suivant manquant.
SECTION_ORDER = ["intro", "mind", "mind and head", "head", "head and stomach", "vertigo", "scalp", "eyes",
    "vision", "ears", "nose", "nose and throat", "face", "mouth", "teeth", "tongue", "throat", "larynx",
    "stomach", "gastric", "abdomen", "stool", "rectum", "urine", "urinary", "kidneys", "bladder", "male",
    "female", "sexual", "respiratory", "respiratory organs", "chest", "heart", "circulation", "neck", "back",
    "back and extremities", "extremities", "limbs", "nerves", "sleep", "skin", "glands", "tissues", "blood",
    "fever", "generalities", "modalities", "relationship", "comparison", "dose", "extra homoeopathic uses"]
SEC_POS = {k: n for n, k in enumerate(SECTION_ORDER)}
END_SECTIONS = {"modalities", "relationship", "dose"}
EXPECTED_LONG_DOSE = {"Belladonna", "Strychninum"}      # paragraphes "usages non homéopathiques"

def order_restart(r):
    keys = [k for k in r["sections"] if k in SEC_POS]
    for a, b in zip(keys, keys[1:]):
        if SEC_POS[a] - SEC_POS[b] >= 12:
            return a, b
    return None

# --- Validation : un problème = une ligne
issues = []
sizes = sorted(sum(len(t) for t in r["sections"].values()) for r in remedies)
p99 = sizes[int(len(sizes) * 0.99) - 1] if sizes else 0
for r in remedies:
    size = sum(len(t) for t in r["sections"].values())
    def issue(kind, detail=""):
        issues.append({"remedy": r["remedy"], "probleme": kind, "detail": detail})
    if r.get("cut_chars"):
        issue("fin de livre coupée après la Dose", f"{r['cut_chars']:,} car. retirés : {r['cut_preview'][:120]}")
    rs = order_restart(r)
    if rs and rs[0] in END_SECTIONS:
        issue("remède fusionné probable (en-tête suivant manquant)", f"'{rs[1]}' après '{rs[0]}'")
    elif rs:
        issue("ordre des sections inhabituel", f"'{rs[1]}' après '{rs[0]}'")
    if len(r["sections"].get("dose", "")) > 600 and r["remedy"] not in EXPECTED_LONG_DOSE:
        issue("Dose anormalement longue (en-tête suivant manquant ?)", f"{len(r['sections']['dose'])} car.")
    if size > 3 * max(p99, 1):
        issue("texte anormalement long", f"{size:,} car. (p99 = {p99:,})")
    if len(r["sections"]) <= 1 and size < 80:
        issue("quasi vide", f"{size} car.")
    if r["ocr"]["score"] is not None and r["ocr"]["score"] < 0.75:
        issue("OCR globalement douteux", f"score {r['ocr']['score']}")
    if not r.get("page_start"):
        issue("page source inconnue")
    if r["name_review"]:
        issue("nom à vérifier", r["header_raw"])
validation = pd.DataFrame(issues, columns=["remedy", "probleme", "detail"])

# Les anomalies du rapport sont aussi portées par chaque fiche (validation_issues) ;
# toutes rendent la fiche "à relire", sauf la coupure de fin de livre (déjà traitée, informative)
INFO_ONLY = {"fin de livre coupée après la Dose"}
by_remedy = {}
for it in issues:
    by_remedy.setdefault(it["remedy"], []).append({"probleme": it["probleme"], "detail": it["detail"]})
for r in remedies:
    r["validation_issues"] = by_remedy.get(r["remedy"], [])
    for it in r["validation_issues"]:
        if it["probleme"] in INFO_ONLY or it["probleme"] == "OCR globalement douteux":
            continue                                   # OCR déjà couvert par le seuil REVIEW_OCR_MIN
        if it["probleme"] not in r["review_reasons"]:
            r["review_reasons"].append(it["probleme"])
    r["needs_review"] = bool([x for x in r["review_reasons"] if not x.startswith("posologie")])
    if r.get("cut_chars"):
        r["correction_status"] = "Bloc parasite de fin de livre déjà retiré ; conserver une vérification visuelle."
n_rev = sum(r["needs_review"] for r in remedies)
print(f"\nFiches à relire (needs_review) : {n_rev} / {len(remedies)} "
      f"(OCR < {REVIEW_OCR_MIN} : {sum(any(x.startswith('OCR') for x in r['review_reasons']) for r in remedies)}, "
      f"nom incertain : {sum(r['name_review'] for r in remedies)})")
print(f"\n=== Validation : {len(validation)} signalement(s) ===")
if len(validation):
    print(validation["probleme"].value_counts().to_string())

zing = next((r for r in remedies if r["remedy"].startswith("Zingiber")), None)
if zing:
    print(f"\nZingiber : {len(zing['sections'])} sections, {sum(len(t) for t in zing['sections'].values()):,} car., "
          f"{zing['source_ref']['pages']}, coupé après la Dose : {zing.get('cut_chars', 0):,} car.")
    if zing.get("cut_preview"):
        print("  Début du texte retiré :", zing["cut_preview"][:200])

tot = Counter()
for r in remedies:
    tot.update({k: r["ocr"][k] for k in ("fiable", "a_verifier", "douteux")})
print(f"Phrases : {tot['fiable']:,} fiables, {tot['a_verifier']:,} à vérifier, {tot['douteux']:,} douteuses")

# ------------------------------------------------------------
# 4. Rapport qualité
# ------------------------------------------------------------
print(f"\nRemèdes détectés : {len(remedies)}")
print(f"Lignes symptômes : {len(sym):,}")
review = pd.DataFrame([{"remedy": r["remedy"], "header_raw": r["header_raw"],
                        "common_name": r["common_name"], "n_sections": len(r["sections"])}
                       for r in remedies if r["needs_review"]])
print(f"Noms OCR à vérifier : {len(review)}")
print("\nSections les plus fréquentes :")
print(sym["section"].value_counts().head(25).to_string())
thin = [r["remedy"] for r in remedies if len(r["sections"]) <= 1]
print(f"\nRemèdes sans section détectée (à contrôler) : {len(thin)} -> {thin[:15]}")

for name in ("Moschus", "Murex"):
    m = next((r for r in remedies if r["remedy"] == name), None)
    if m:
        print(f"{name} : {len(m['sections'])} sections, dose = {m['sections'].get('dose', '')[:80]!r}")

aco = next((r for r in remedies if r["remedy"].startswith("Aconitum")), None)
if aco:
    print("\n--- Contrôle : Aconitum Napellus ---")
    print("Sections :", list(aco["sections"].keys()))
    print("Pire     :", aco["worse"])
    print("Mieux    :", aco["better"])
    print("Relation :", aco["relationship"])

# ------------------------------------------------------------
# 5. Recherche FR -> EN (vocabulaire du texte de 1906)
# ------------------------------------------------------------
FR_EN = {
    "toux": "cough", "nuit": "night", "fièvre": "fever", "fievre": "fever",
    "mal de tête": "headache", "céphalée": "headache", "migraine": "headache",
    "gorge": "throat", "nausée": "nausea", "vomissement": "vomit",
    "diarrhée": "diarrh", "constipation": "constipation", "rhume": "coryza",
    "éternuement": "sneez", "insomnie": "sleepless", "anxiété": "anxi",
    "peur": "fear", "tristesse": "sad", "vertige": "vertigo",
    "démangeaison": "itch", "brûlure": "burning", "contusion": "bruise",
    "ecchymose": "bruise", "douleur": "pain", "froid": "cold", "chaleur": "heat",
    "soir": "evening", "matin": "morning", "yeux": "eye", "oeil": "eye",
    "oreille": "ear", "nez": "nose", "estomac": "stomach", "ventre": "abdomen",
    "dos": "back", "peau": "skin", "règles": "menses", "hémorroïdes": "haemorrhoid",
    "enrouement": "hoarse", "sueur": "sweat", "transpiration": "perspiration",
    "soif": "thirst", "faiblesse": "weak", "crampe": "cramp", "piqûre": "sting",
    "gonflement": "swell", "saignement": "bleed", "rhumatisme": "rheumat",
    "articulation": "joint", "foie": "liver", "coeur": "heart", "palpitation": "palpitation",
}

STOP_EN = {"the", "and", "with", "of", "in", "a", "on", "at", "to", "from"}

def to_stems(query):
    q = query.lower()
    stems = []
    for fr, en in sorted(FR_EN.items(), key=lambda kv: -len(kv[0])):
        if fr in q:
            stems.append(en)
            q = q.replace(fr, " ")
    stems += [w for w in re.findall(r"[a-z]{3,}", q) if w not in STOP_EN]
    return list(dict.fromkeys(stems))

sym["_txt"] = sym["symptom"].str.lower()

def search(query, top=10):
    stems = to_stems(query)
    if not stems:
        return pd.DataFrame()
    pats = [re.compile(r"\b" + re.escape(s)) for s in stems]
    s = sym.copy()
    s["hits"] = s["_txt"].apply(lambda x: sum(1 for p in pats if p.search(x)))
    s = s[s["hits"] > 0]
    agg = (s.groupby("remedy")
             .agg(best=("hits", "max"), n=("hits", "size"),
                  examples=("symptom", lambda x: " | ".join(x.head(3))))
             .assign(score=lambda d: d["best"] * 10 + d["n"])
             .sort_values("score", ascending=False)
             .head(top))
    print(f"Recherche '{query}' -> termes {stems}")
    return agg[["score", "best", "n", "examples"]]

print(search("toux nuit").to_string())

# ------------------------------------------------------------
# 6. Export pour l'app HTML/JS
# ------------------------------------------------------------
export = {
    "source": SOURCE_META,
    "remedies": [{k: r.get(k) for k in ("remedy", "common_name", "name_status", "needs_review", "review_reasons",
                                        "validation_issues", "correction_status", "corrections_ocr",
                                        "source_ref", "ocr", "lines", "sections",
                                        "worse", "better", "relationship", "posologie_hors_dose")}
                 for r in remedies],
}
export["source"]["ocr_niveaux"] = "fiable >= 0.90 ; à vérifier 0.75-0.90 ; douteux < 0.75 (part de mots reconnus)"
export["source"]["needs_review"] = (f"true si nom incertain, score OCR moyen < {REVIEW_OCR_MIN}, "
                                    "ordre des sections inhabituel ou fiche quasi vide (détail dans review_reasons, "
                                    "anomalies du rapport dans validation_issues)")
export["source"]["posologie_hors_dose"] = ("mentions de posologie trouvées hors section Dose : retirées de sections/lines, "
                                           "conservées ici pour traçabilité, jamais affichées")
with open("boericke_remedies.json", "w", encoding="utf-8") as f:
    json.dump(export, f, ensure_ascii=False)
sym.drop(columns="_txt").to_csv("boericke_symptoms.csv", index=False, encoding="utf-8")
review.to_csv("boericke_review.csv", index=False, encoding="utf-8")
validation.to_csv("boericke_validation.csv", index=False, encoding="utf-8")
if not os.path.exists(FIX_CSV):                    # ne jamais écraser une feuille en cours de saisie
    a_corriger.to_csv(FIX_CSV, index=False, encoding="utf-8-sig")
else:
    a_corriger.to_csv("boericke_a_corriger_nouveau.csv", index=False, encoding="utf-8-sig")

from google.colab import files
for fn in ("boericke_remedies.json", "boericke_symptoms.csv", "boericke_review.csv", "boericke_validation.csv",
           FIX_CSV if not os.path.exists("boericke_a_corriger_nouveau.csv") else "boericke_a_corriger_nouveau.csv"):
    files.download(fn)
