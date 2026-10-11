# Homeo Explorer

Outil **documentaire** de recherche plein texte dans une materia medica homéopathique historique :
*Pocket Manual of Homoeopathic Materia Medica*, William Boericke, 3e édition, 1906 (domaine public,
scan de l'Internet Archive).

> **Ce n'est pas un outil de prescription.** Il montre ce qu'un ouvrage de 1906 affirmait, avec la page
> source. Les posologies sont masquées. Le nombre de publications PubMed indique qu'un sujet a été étudié,
> pas qu'un remède est efficace. En cas de symptôme sérieux : médecin, pharmacien ou 112.

## Contenu

| Fichier | Rôle |
|---|---|
| `homeo-explorer.html` | Application (un seul fichier HTML/JS, sans dépendance). Ouvrir dans le navigateur, puis charger `data/boericke_remedies.json`. |
| `homeo-explorer_bm25.html` | Variante en test : classement BM25 (mots rares et passages qui réunissent les termes). |
| `data/boericke_remedies.json` | 606 remèdes : sections, phrases avec score OCR, page source, posologies retirées hors section Dose (tracées), `needs_review` et `review_reasons`. Intègre 1 343 corrections d'OCR tracées dans `corrections_ocr` (origine indiquée pour chacune). |
| `data/boericke_validation.csv` | Anomalies détectées par le parser (ordre des sections, OCR douteux, fiche quasi vide…). |
| `data/boericke_a_corriger.csv` | Feuille de correction OCR : phrases sous 0.90, avec page et lien vers le scan. |
| `data/boericke_a_corriger_homeoint.csv` | Même feuille, pré-remplie avec des corrections alignées sur la transcription homeoint.org (9e éd., 1927) : 1 342 corrections d'OCR pur pré-validées (23 retirées car elles perdaient un mot de 1906), le reste à décider (`note_ia`). |
| `data/boericke_symptoms.csv`, `data/boericke_review.csv` | Table des symptômes, revue des noms. |
| `scripts/boericke_parser_complet.py` | Parser Google Colab : texte OCR → JSON (détection des remèdes, pagination, qualité OCR, filtrage des posologies, validation). |
| `scripts/boericke_correction_ia.py` | Propositions de correction OCR par IA (API Anthropic), à valider à la main dans la feuille. |
| `scripts/boericke_enrichir.py` | (En attente) traduction française automatique et statut BDPM. |
| `outils/controle_etape1_echantillon.py` | Contrôle qualité : tire un échantillon aléatoire stratifié (6 strates × 50). |
| `outils/correction_ocr.html` | Page de correction des phrases OCR douteuses : texte OCR, proposition éventuelle avec différences surlignées, lien vers le scan, saisie de la correction, export de la feuille pour le parser. |
| `outils/controle_relecture.html` | Page de relecture de l'échantillon (ok / erreur, lien vers le scan, taux d'erreur avec IC 95 %, export CSV). |

## Contrôle qualité

Contrôle par échantillon aléatoire, vérifié à la main sur le scan de 1906 :

| Strate | Contrôlés | Erreurs | Taux d'erreur (IC 95 %) |
|---|---|---|---|
| Corrections d'OCR (1 343, alignées sur homeoint.org puis filtrées : aucun mot ajouté ni retiré) | 50 | 0 | 0 % (≤ 7,1 %) |

Les autres strates (limites des remèdes, posologies retirées, noms, phrases) restent à contrôler.

## Régénérer les données (Colab)

1. `files.upload()` : `boericke_parser_complet.py` (+ `boericke_a_corriger.csv` si des corrections y sont saisies).
2. `exec(open("boericke_parser_complet.py", encoding="utf-8").read())` : le texte OCR est téléchargé depuis l'Internet Archive.

## Corriger l'OCR

- À la main : remplir `texte_corrige` dans `boericke_a_corriger.csv`.
- Avec l'IA : lancer `boericke_correction_ia.py` (clé `ANTHROPIC_API_KEY` dans les Secrets Colab), puis mettre `o`
  dans la colonne `valider` pour chaque proposition acceptée. La correction manuelle reste prioritaire.
- Relancer le parser avec la feuille : chaque correction est tracée (`corrections_ocr`, origine manuelle ou IA).

## Sources

- Boericke W., *Pocket Manual of Homoeopathic Materia Medica*, 1906 — https://archive.org/details/pocketmanualhom00boergoog
- PubMed E-utilities (NCBI) pour le comptage des publications indexées.
