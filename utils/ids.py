"""Conventions canonical_id + generation deterministe pour les noeuds de reification."""

import hashlib
import unicodedata


def normalize_id(value: str | None) -> str | None:
    """minuscules, sans accents, sans espaces -> underscores."""
    if not value:
        return None
    value = unicodedata.normalize("NFD", value)
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    value = value.lower().strip()
    for ch in [" ", "-", "'", "/"]:
        value = value.replace(ch, "_")
    while "__" in value:
        value = value.replace("__", "_")
    return value.strip("_")


def _hash(*parts: str | None, prefix: str, length: int = 12) -> str:
    key = "|".join((p or "").strip().lower() for p in parts)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def evaluation_canonical_id(medicament_id: str, pathologie_id: str, population_id: str,
                             document_id: str, date_avis: str | None) -> str:
    """Deterministe : un meme (medicament, pathologie, population, document, date) redonne
    toujours le meme id -> permet le dedoublonnage MERGE entre plusieurs runs.

    Inclut population_id : un meme document peut juger plusieurs sous-populations de la
    meme pathologie a la meme date avec des SMR/ASMR distincts (ex: sous-groupe EGFR+ vs
    ALK+ dans un meme avis) — sans population_id dans la cle, ces evaluations distinctes
    collisionneraient sur le meme canonical_id.
    """
    return _hash(medicament_id, pathologie_id, population_id, document_id, date_avis, prefix="eval")


def population_canonical_id(profil_genetique: str | None, sous_groupe: str | None, gravite: str | None) -> str:
    """Deterministe sur le contenu -> permet le dedoublonnage inter-documents
    d'une population decrite de facon identique."""
    if not any([profil_genetique, sous_groupe, gravite]):
        return "population_non_precisee"
    return _hash(profil_genetique, sous_groupe, gravite, prefix="pop")


def argument_canonical_id(categorie: str, orientation: str, type_argument: str) -> str:
    """Deterministe sur (categorie, orientation, type_argument) -- PAS sur le texte
    verbatim. type_argument vient d'une taxonomie fermee (utils/arguments_taxonomy.py) :
    c'est ce qui permet a deux formulations differentes du meme argument de fusionner
    sur le meme noeud Argument. Le texte verbatim par instance est porte par la
    relation INVOQUE, pas par l'identite du noeud."""
    return _hash(categorie, orientation, type_argument, prefix="arg", length=16)
