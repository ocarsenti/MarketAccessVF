"""Extraction d'un avis de la Commission de la Transparence HAS (SMR/ASMR) vers
le schema graphe cible : Medicament / Pathologie / Comparateur / Evaluation /
Population / Argument (voir docs/schema.md).

Reprend de l'ancien extract_has.py (has-market-access) le principe qui
fonctionnait : envoyer le PDF directement en document au modele, avec un
prompt qui interdit toute completion par connaissances generales. Le JSON de
sortie est entierement restructure pour reifier Evaluation / Population /
Argument au lieu de les coller en attributs texte libre.
"""

import base64
import json
import os
import sys
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.ids import (
    argument_canonical_id,
    evaluation_canonical_id,
    normalize_id,
    population_canonical_id,
)
from utils.pathologies import pathologie_canonical_id, resolve_icd10
from utils.arguments_taxonomy import resolve_type_argument, label_for, taxonomie_prompt_text

load_dotenv(override=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = "claude-sonnet-5"

# Sonnet 5 pricing (2026-09) : $2 / MTok input, $10 / MTok output.
PRICE_IN_PER_MTOK = 2.0
PRICE_OUT_PER_MTOK = 10.0

_COST_LOG = Path(__file__).parent.parent / "data" / "extraction_costs.json"

_RULES = """Tu es un expert en evaluation medicale et market access pharmaceutique en France.
Tu analyses un avis de la Commission de la Transparence de la HAS (medicaments, SMR/ASMR)
et tu extrais les informations dans un format JSON structure strict.

REGLES ABSOLUES :
- N'extrais QUE ce qui est explicitement ecrit dans le document.
- Ne complete JAMAIS avec des connaissances medicales generales : si le PDF ne le dit pas, mets null.
- Un medicament peut avoir plusieurs indications dans le meme avis (ou le meme document peut
  juger plusieurs sous-populations distinctes) : cree une entree distincte dans "evaluations"
  pour CHAQUE couple (indication x jugement SMR/ASMR), meme si smr/asmr sont identiques.
- N'invente JAMAIS de code ICD10 : laisse "icd10" a null, indique seulement le nom de la
  pathologie tel qu'ecrit dans le document (la resolution ICD10 se fait ensuite par dictionnaire).
- Retourne UNIQUEMENT le JSON, sans texte avant ni apres, sans balises markdown.

DATES :
- "date_avis" : date COMPLETE de l'avis au format ISO YYYY-MM-DD si le document donne le jour.
  Si seul le mois est connu : YYYY-MM. Si seule l'annee est connue (rare) : YYYY.
  Ne devine JAMAIS un jour ou un mois arbitraire.
- "date_avis_precision" : "jour" / "mois" / "annee" selon la precision reellement disponible.

VALEURS AUTORISEES :
- smr_niveau : "Important" / "Modere" / "Faible" / "Insuffisant" / null
- asmr_valeur : "I" / "II" / "III" / "IV" / "V" / "NA" (NA = pas d'ASMR : refus, acces precoce, etc.)
- type_avis : "primo-inscription" / "renouvellement" / "extension-indication" / "reevaluation" /
  "acces-precoce" / "refus-acces-precoce" / "nouvel-examen" / "non-sollicite" / "reevaluation-commission"
- categorie (Argument) : "methodologie" / "efficacite" / "securite" / "besoin_medical_non_couvert" / "autre"
- orientation (Argument) : "favorable" / "defavorable"

CANONICAL_ID (medicament, comparateur) : convention stricte, minuscules, underscores,
sans accents, sans espaces, DCI de preference. Ex: "pembrolizumab", "bevacizumab".

ARGUMENTS :
Extrais CHAQUE argument favorable ou defavorable evoque par la commission comme un objet
separe et court (une phrase, pas un paragraphe), avec sa categorie, son orientation, ET
un "type_argument" choisi dans la taxonomie fermee ci-dessous (obligatoire — c'est ce qui
permet de regrouper le meme type d'argument meme s'il est formule differemment d'un avis
a l'autre). Choisis le type le plus proche ; utilise "autre"/"autre" UNIQUEMENT si vraiment
aucun type ne correspond. Ne fusionne jamais plusieurs arguments distincts dans un seul texte.

TAXONOMIE FERMEE (categorie -> type_argument) :
""" + taxonomie_prompt_text() + """
"""

_STRUCTURE = """
STRUCTURE JSON ATTENDUE :
{
  "document_info": {
    "titre": "titre exact du document",
    "type_document": "avis de la commission de la transparence"
  },
  "medicament": {
    "canonical_id": "dci_minuscules_underscores",
    "nom": "nom commercial",
    "dci": "denomination commune internationale",
    "fabricant": null,
    "type_molecule": null
  },
  "evaluations": [
    {
      "pathologie": {
        "nom": "nom de la pathologie/indication tel qu'ecrit dans le PDF",
        "icd10": null,
        "categorie": "ex: oncologie, rhumatologie, cardiologie... si deductible du contexte, sinon null",
        "severite": null
      },
      "population": {
        "profil_genetique": "ex: mutation EGFR, ALK+, null si non mentionne",
        "sous_groupe": "ex: adultes en echec de premiere ligne, null si non mentionne",
        "gravite": "ex: forme severe / maladie rare, null si non mentionne"
      },
      "smr_niveau": "Important / Modere / Faible / Insuffisant / null",
      "asmr_valeur": "I / II / III / IV / V / NA",
      "asmr_signification": "phrase courte de justification de la valeur ASMR telle que donnee par la commission",
      "date_avis": "YYYY-MM-DD (ou YYYY-MM ou YYYY si moins precis)",
      "date_avis_precision": "jour / mois / annee",
      "type_avis": "primo-inscription / renouvellement / ...",
      "ligne_traitement": "ex: premiere ligne, apres echec d'au moins une ligne anterieure ; null si non mentionne",
      "justification": "resume court (1-3 phrases) des motifs generaux de la conclusion de la commission",
      "arguments": [
        {
          "texte": "argument court, une phrase, verbatim ou tres proche du PDF",
          "categorie": "methodologie / efficacite / securite / besoin_medical_non_couvert / autre",
          "orientation": "favorable / defavorable",
          "type_argument": "code de la taxonomie fermee (voir liste plus haut), obligatoire"
        }
      ],
      "comparateurs": [
        {
          "comparateur": {
            "canonical_id": "dci_minuscules_underscores",
            "nom": "nom",
            "dci": "dci",
            "type_molecule": null
          },
          "en_association_avec": null,
          "role": "ex: comparateur de l'etude pivot / alternative therapeutique citee par la commission",
          "endpoint_principal": "ex: OS, PFS, ORR ; null si non mentionne",
          "endpoint_secondaires": ["..."],
          "resultat_principal": "resultat chiffre verbatim (HR, mediane...) si mentionne, sinon null",
          "resultat_secondaires": "texte libre court, sinon null",
          "evidence_excerpt": "passage exact du PDF (1-2 phrases) etayant ce resultat, sinon null"
        }
      ]
    }
  ]
}

Si aucune indication/evaluation n'est clairement identifiable dans le document (ex: document
purement administratif), retourne "evaluations": [] plutot que d'inventer une entree.
Retourne UNIQUEMENT le JSON complet, sans texte autour.
"""


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _log_cost(document_id: str, tokens_in: int, tokens_out: int, cost: float) -> None:
    _COST_LOG.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    if _COST_LOG.exists():
        try:
            entries = json.loads(_COST_LOG.read_text(encoding="utf-8"))
        except Exception:
            entries = []
    entries.append({
        "document_id": document_id,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": round(cost, 5),
        "model": MODEL,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    _COST_LOG.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def _postprocess(data: dict, document_id: str) -> dict:
    """Resout les canonical_id derives (pathologie, evaluation, population, argument)
    en Python plutot que de faire confiance au LLM pour ces valeurs deterministes."""
    med = data.get("medicament") or {}
    med["canonical_id"] = normalize_id(med.get("canonical_id") or med.get("dci") or med.get("nom"))
    data["medicament"] = med
    med_id = med["canonical_id"]

    for ev in data.get("evaluations", []):
        path = ev.get("pathologie") or {}
        icd10, matched = resolve_icd10(path.get("nom"), document_id=document_id)
        path["icd10"] = icd10
        path["icd10_resolu_automatiquement"] = matched
        path["canonical_id"] = pathologie_canonical_id(path.get("nom") or "inconnue", icd10)
        ev["pathologie"] = path

        pop = ev.get("population") or {}
        if any([pop.get("profil_genetique"), pop.get("sous_groupe"), pop.get("gravite")]):
            pop_id = population_canonical_id(
                pop.get("profil_genetique"), pop.get("sous_groupe"), pop.get("gravite"))
            pop["canonical_id"] = pop_id
            ev["population"] = pop
        else:
            pop_id = "population_non_precisee"
            ev["population"] = None

        ev["canonical_id"] = evaluation_canonical_id(
            med_id, path["canonical_id"], pop_id, document_id, ev.get("date_avis"))

        for arg in ev.get("arguments", []):
            categorie = arg.get("categorie") or "autre"
            orientation = arg.get("orientation") or "favorable"
            type_argument, matched = resolve_type_argument(
                categorie, arg.get("type_argument"), arg.get("texte"), document_id=document_id)
            arg["type_argument"] = type_argument
            arg["type_argument_resolu_automatiquement"] = matched
            arg["label"] = label_for(categorie, type_argument)
            arg["canonical_id"] = argument_canonical_id(categorie, orientation, type_argument)

        for comp_entry in ev.get("comparateurs", []):
            comp = comp_entry.get("comparateur") or {}
            comp["canonical_id"] = normalize_id(comp.get("canonical_id") or comp.get("dci") or comp.get("nom"))
            comp_entry["comparateur"] = comp

    return data


def extract_from_pdf(pdf_path: str, output_dir: str = "data/json") -> str:
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF non trouve : {pdf_path}")

    document_id = pdf_path.stem
    output_dir_path = Path(output_dir)
    output_path = output_dir_path / f"{document_id}.json"
    if output_path.exists():
        print(f"SKIP — deja extrait : {document_id}")
        return str(output_path)

    print(f"\n{'='*60}\nPDF : {pdf_path.name}")

    with open(pdf_path, "rb") as f:
        pdf_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = _RULES + "\n\n" + _STRUCTURE

    for attempt in range(5):
        try:
            msg = client.messages.create(
                model=MODEL,
                max_tokens=8000,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "document", "source": {
                            "type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
            break
        except anthropic.RateLimitError:
            wait = 30 * (2 ** attempt)
            print(f"  Rate limit — attente {wait}s (tentative {attempt + 1}/5)...")
            time.sleep(wait)
            if attempt == 4:
                raise

    text_blocks = [b.text for b in msg.content if b.type == "text"]
    if not text_blocks:
        raise RuntimeError(f"Aucun bloc texte dans la reponse (types recus : "
                            f"{[b.type for b in msg.content]})")
    raw = _strip_fences("".join(text_blocks))
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Erreur JSON : {e}\nReponse brute (500 car.) : {raw[:500]}")
        raise

    data["document_info"]["document_id"] = document_id
    data["document_info"]["source_pdf"] = pdf_path.name
    data = _postprocess(data, document_id)

    tokens_in = msg.usage.input_tokens
    tokens_out = msg.usage.output_tokens
    cost = (tokens_in * PRICE_IN_PER_MTOK + tokens_out * PRICE_OUT_PER_MTOK) / 1_000_000
    _log_cost(document_id, tokens_in, tokens_out, cost)

    print(f"  Evaluations extraites : {len(data.get('evaluations', []))}")
    print(f"  Tokens : {tokens_in} in / {tokens_out} out — cout ${cost:.4f}")

    output_dir_path.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  JSON sauvegarde : {output_path}")

    return str(output_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extraction/extract_has.py <pdf> [output_dir]")
        sys.exit(1)
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "data/json"
    extract_from_pdf(sys.argv[1], out_dir)
