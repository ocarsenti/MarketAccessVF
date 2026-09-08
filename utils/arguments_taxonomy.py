"""Taxonomie fermee pour Argument.type_argument.

Meme principe que utils/pathologies.py : le LLM classe chaque argument dans
une liste fermee (fournie dans le prompt), mais on NE FAIT PAS confiance
aveuglement a sa sortie -> tout code hors taxonomie (hallucination, typo, ou
"autre" explicite) est renvoye a "autre" et logge pour extension manuelle,
plutot que de laisser une valeur non controlee polluer le graphe.

C'est ce champ (pas le texte verbatim) qui determine l'identite du noeud
Argument -> deux formulations differentes du meme type d'argument
("absence de comparateur direct" / "pas de donnee comparative versus le
traitement de reference") fusionnent desormais sur le meme noeud.
"""

import json
from pathlib import Path

_LOG_PATH = Path(__file__).parent.parent / "data" / "arguments_a_verifier.json"

# categorie -> {type_argument: label FR lisible}
TAXONOMIE: dict[str, dict[str, str]] = {
    "methodologie": {
        "absence_comparateur_direct": "Absence de comparaison directe avec le traitement de reference",
        "comparateur_non_pertinent": "Comparateur juge non pertinent ou obsolete",
        "etude_non_randomisee": "Etude non randomisee / bras unique",
        "etude_ouverte_absence_aveugle": "Etude ouverte, absence d'aveugle",
        "effectif_insuffisant": "Effectif de l'etude insuffisant",
        "sous_groupe_non_analysable": "Sous-groupe trop petit pour etre analyse",
        "critere_principal_inadapte": "Critere de jugement principal juge inadapte",
        "donnees_immatures": "Donnees de survie/efficacite immatures",
        "extrapolation_hors_amm": "Extrapolation au-dela des donnees/de l'AMM",
        "transposabilite_limitee": "Transposabilite limitee a la pratique clinique francaise",
        "risque_de_biais": "Risque de biais methodologique identifie",
        "resultats_non_matures_ou_incertains": "Resultats non matures ou incertitude statistique residuelle",
    },
    "efficacite": {
        "superiorite_demontree": "Superiorite demontree sur le critere principal",
        "non_inferiorite_demontree": "Non-inferiorite demontree",
        "absence_benefice_demontre": "Absence de benefice clinique demontre",
        "effet_taille_incertain": "Incertitude sur la taille de l'effet",
        "benefice_clinique_modeste": "Benefice clinique juge modeste",
        "resultats_non_significatifs": "Resultats non statistiquement significatifs",
        "resultats_prometteurs_mais_precoces": "Resultats prometteurs mais precoces",
    },
    "securite": {
        "profil_tolerance_favorable": "Profil de tolerance favorable",
        "profil_tolerance_defavorable": "Profil de tolerance defavorable",
        "effets_indesirables_graves": "Effets indesirables graves rapportes",
        "donnees_securite_insuffisantes": "Donnees de securite insuffisantes / recul limite",
    },
    "besoin_medical_non_couvert": {
        "maladie_grave_pronostic_vital": "Maladie grave engageant le pronostic vital",
        "absence_alternative_therapeutique": "Absence d'alternative therapeutique",
        "besoin_partiellement_couvert": "Besoin medical partiellement couvert",
        "besoin_deja_couvert": "Besoin medical deja couvert par les alternatives existantes",
        "alternatives_disponibles": "Alternatives therapeutiques disponibles",
    },
    "autre": {
        "autre": "Argument ne correspondant a aucune categorie fermee existante",
    },
}


def taxonomie_prompt_text() -> str:
    lines = []
    for categorie, types in TAXONOMIE.items():
        lines.append(f"  {categorie} :")
        for code, label in types.items():
            lines.append(f"    - {code} : {label}")
    return "\n".join(lines)


def resolve_type_argument(categorie: str | None, type_argument: str | None,
                           texte: str | None, document_id: str | None = None) -> tuple[str, bool]:
    """Valide type_argument contre la taxonomie fermee.

    Retourne (type_argument_valide, matched). Si non reconnu (hallucination,
    typo, ou "autre" explicite du LLM), retourne ("autre", False) et logge
    l'occurrence pour extension manuelle de la taxonomie.
    """
    categorie = categorie or "autre"
    valid_for_cat = TAXONOMIE.get(categorie, {})

    if type_argument and type_argument in valid_for_cat:
        return type_argument, True

    # tolere une classification dans une autre categorie que celle indiquee
    for cat_types in TAXONOMIE.values():
        if type_argument and type_argument in cat_types:
            return type_argument, True

    _log_unknown(categorie, type_argument, texte, document_id)
    return "autre", False


def label_for(categorie: str, type_argument: str) -> str:
    return TAXONOMIE.get(categorie, {}).get(type_argument) or TAXONOMIE["autre"]["autre"]


def _log_unknown(categorie: str, type_argument: str | None, texte: str | None, document_id: str | None) -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    if _LOG_PATH.exists():
        try:
            entries = json.loads(_LOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            entries = []

    entries.append({
        "categorie_proposee": categorie,
        "type_argument_llm": type_argument,
        "texte": texte,
        "document_id": document_id,
    })
    _LOG_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
