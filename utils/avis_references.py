"""Resolution des references croisees entre avis HAS (relation S_APPUIE_SUR).

Quand un avis cite un AUTRE avis HAS (sur un medicament different) comme
source d'une partie de son calcul de population cible (ex: Mounjaro citant
Victoza 2015 et Ozempic 2022), l'avis reference n'est pas forcement deja
present dans le graphe au moment de l'extraction. On cree un noeud
Evaluation "placeholder", identifie uniquement par (medicament, annee) --
PAS par le canonical_id complet d'une vraie Evaluation, qui depend aussi de
pathologie/population/document/date_avis, inconnus tant que l'avis
reference n'a pas ete lui-meme extrait -- et on logge la reference dans
data/avis_references_a_verifier.json pour reconciliation manuelle
ulterieure avec la vraie Evaluation une fois celle-ci extraite. Meme
principe que utils/pathologies.py / utils/arguments_taxonomy.py.
"""

import json
from pathlib import Path

from .ids import _hash, normalize_id

_LOG_PATH = Path(__file__).parent.parent / "data" / "avis_references_a_verifier.json"


def placeholder_evaluation_canonical_id(medicament_nom: str, annee: str | None) -> str:
    """Deterministe sur (medicament, annee) uniquement. Prefixe distinct de
    evaluation_canonical_id() ('eval_placeholder_' vs 'eval_') pour ne jamais
    collisionner avec le canonical_id d'une vraie Evaluation."""
    return _hash(normalize_id(medicament_nom), annee, prefix="eval_placeholder")


def log_reference(medicament_nom: str, annee: str | None, contexte: str | None,
                   source_document_id: str | None) -> str:
    """Logge la reference pour reconciliation manuelle et retourne le canonical_id
    du noeud Evaluation placeholder a creer/relier."""
    canonical_id = placeholder_evaluation_canonical_id(medicament_nom, annee)

    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    if _LOG_PATH.exists():
        try:
            entries = json.loads(_LOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            entries = []

    for e in entries:
        if e.get("canonical_id") == canonical_id:
            if source_document_id and source_document_id not in e.get("cite_par", []):
                e.setdefault("cite_par", []).append(source_document_id)
            _LOG_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
            return canonical_id

    entries.append({
        "canonical_id": canonical_id,
        "medicament_nom": medicament_nom,
        "annee": annee,
        "contexte": contexte,
        "cite_par": [source_document_id] if source_document_id else [],
    })
    _LOG_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    return canonical_id
