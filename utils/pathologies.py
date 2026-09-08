"""Dictionnaire de normalisation Pathologie -> ICD10.

Le LLM d'extraction NE DOIT JAMAIS inventer un code ICD10 : il renvoie le nom
de la pathologie tel qu'il apparait dans le PDF (`nom`), et c'est ce module
qui tente une correspondance contre un dictionnaire controle. Toute
pathologie non reconnue est loggee dans data/pathologies_a_verifier.json
pour extension manuelle ulterieure, plutot que de laisser le LLM deviner.
"""

import json
import unicodedata
from pathlib import Path

_LOG_PATH = Path(__file__).parent.parent / "data" / "pathologies_a_verifier.json"

# Dictionnaire de reference. Cles normalisees (minuscules, sans accents).
# Perimetre Commission de la Transparence : pas uniquement oncologie.
PATHOLOGIES_ICD10: dict[str, str] = {
    # Oncologie
    "cancer bronchique non a petites cellules": "C34",
    "cbnpc": "C34",
    "nsclc": "C34",
    "cancer du poumon": "C34",
    "poumon": "C34",
    "cancer bronchique a petites cellules": "C34.9",
    "melanome": "C43",
    "melanome cutane": "C43",
    "lymphome diffus a grandes cellules b": "C83.3",
    "ldgcb": "C83.3",
    "dlbcl": "C83.3",
    "cancer colorectal": "C18",
    "colorectal": "C18",
    "cancer du colon": "C18",
    "cancer du rectum": "C20",
    "cancer du sein": "C50",
    "cancer de la prostate": "C61",
    "cancer du pancreas": "C25",
    "cancer de l estomac": "C16",
    "cancer gastrique": "C16",
    "lymphome de hodgkin": "C81",
    "leucemie lymphoide chronique": "C91.1",
    "llc": "C91.1",
    "myelome multiple": "C90.0",
    "cancer du col de l uterus": "C53",
    "cancer du col uterin": "C53",
    "cancer de l ovaire": "C56",
    "cancer de l endometre": "C54",
    "cancer du rein": "C64",
    "carcinome renal": "C64",
    "cancer de la vessie": "C67",
    "carcinome urothelial": "C67",
    "leucemie aigue myeloide": "C92.0",
    "lam": "C92.0",
    "leucemie aigue lymphoblastique": "C91.0",
    "lal": "C91.0",
    "cancer du foie": "C22",
    "carcinome hepatocellulaire": "C22.0",
    "cancer de l oesophage": "C15",
    "cancer de la thyroide": "C73",
    "cancer de la tete et du cou": "C14",
    "sarcome des tissus mous": "C49",
    "mesotheliome": "C45",
    "glioblastome": "C71",
    "cancer du testicule": "C62",
    "lymphome folliculaire": "C82",
    "lymphome du manteau": "C83.1",
    "macroglobulinemie de waldenstrom": "C88.0",
    "syndrome myelodysplasique": "D46",
    "leucemie myeloide chronique": "C92.1",
    "lmc": "C92.1",
    "neuroblastome": "C74.9",
    # Non-oncologie
    "polyarthrite rhumatoide": "M05",
    "spondylarthrite ankylosante": "M45",
    "rhumatisme psoriasique": "L40.5",
    "diabete de type 2": "E11",
    "diabete de type 1": "E10",
    "hypertension arterielle pulmonaire": "I27.0",
    "htap": "I27.0",
    "sclerose en plaques": "G35",
    "maladie de crohn": "K50",
    "rectocolite hemorragique": "K51",
    "psoriasis": "L40",
    "asthme severe": "J45",
    "bronchopneumopathie chronique obstructive": "J44",
    "bpco": "J44",
    "mucoviscidose": "E84",
    "hemophilie a": "D66",
    "hemophilie b": "D67",
    "amylose": "E85",
    "atrophie musculaire spinale": "G12.0",
    "sma": "G12.0",
    "covid-19": "U07.1",
    "infection a vih": "B20",
    "vih": "B20",
    "hepatite b chronique": "B18.1",
    "hepatite c chronique": "B18.2",
    "degenerescence maculaire liee a l age": "H35.3",
    "dmla": "H35.3",
    "insuffisance cardiaque": "I50",
    "fibrillation atriale": "I48",
    "maladie d alzheimer": "G30",
    "maladie de parkinson": "G20",
    "epilepsie": "G40",
    "migraine": "G43",
    "osteoporose": "M81",
    "lupus erythemateux systemique": "M32",
    "syndrome de sjogren": "M35.0",
    "dermatite atopique": "L20",
    "urticaire chronique spontanee": "L50.1",
    "maladie renale chronique": "N18",
    "anemie falciforme": "D57.1",
    "drepanocytose": "D57.1",
    "beta-thalassemie": "D56.1",
    "amyotrophie spinale infantile": "G12.0",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower().strip()
    for ch in ["'", "-", "_"]:
        s = s.replace(ch, " ")
    return " ".join(s.split())


def resolve_icd10(nom_pathologie: str | None, document_id: str | None = None) -> tuple[str | None, bool]:
    """Tente de resoudre `nom_pathologie` vers un code ICD10 controle.

    Retourne (icd10, matched). Si non trouve : icd10=None, matched=False,
    et l'occurrence est loggee dans data/pathologies_a_verifier.json.
    """
    if not nom_pathologie:
        return None, False

    key = _norm(nom_pathologie)
    if key in PATHOLOGIES_ICD10:
        return PATHOLOGIES_ICD10[key], True

    # correspondance partielle (substring dans un sens ou l'autre)
    for k, v in PATHOLOGIES_ICD10.items():
        if k in key or key in k:
            return v, True

    _log_unknown(nom_pathologie, document_id)
    return None, False


def _log_unknown(nom_pathologie: str, document_id: str | None) -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    if _LOG_PATH.exists():
        try:
            entries = json.loads(_LOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            entries = []

    for e in entries:
        if _norm(e.get("nom", "")) == _norm(nom_pathologie):
            if document_id and document_id not in e.get("documents", []):
                e.setdefault("documents", []).append(document_id)
            _LOG_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
            return

    entries.append({
        "nom": nom_pathologie,
        "documents": [document_id] if document_id else [],
    })
    _LOG_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def pathologie_canonical_id(nom_pathologie: str, icd10: str | None) -> str:
    """canonical_id : code ICD10 normalise si connu, sinon slug prefixe (a corriger manuellement)."""
    if icd10:
        return icd10.lower().replace(".", "_").replace(" ", "_")
    slug = _norm(nom_pathologie).replace(" ", "_")
    return f"pathologie_inconnue_{slug}"
