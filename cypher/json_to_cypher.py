"""Convertit les JSON extraits (schema Medicament/Pathologie/Comparateur/
Evaluation/Population/Argument) en instructions Cypher MERGE idempotentes.

Un seul fichier .cypher est genere par JSON, dans data/cypher/. Les
canonical_id deterministes (calcules a l'extraction, voir utils/ids.py)
permettent de rejouer ce script plusieurs fois sans dupliquer de noeuds.

SUCCEDE_A est etabli dans un second temps par link_succede_a(), une fois
tous les JSON convertis, car il faut connaitre l'ensemble des Evaluation
d'un (medicament, pathologie) pour les trier par date_avis croissante.
"""

import json
import sys
from pathlib import Path


def _esc(value) -> str:
    """Echappe une valeur Python vers un litteral Cypher (ou 'null')."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_esc(v) for v in value) + "]"
    s = str(value).replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")
    return f"'{s}'"


def _props(d: dict, keys: list[str]) -> str:
    return ", ".join(f"{k}: {_esc(d.get(k))}" for k in keys)


def medicament_cypher(med: dict) -> str:
    props = _props(med, ["canonical_id", "nom", "dci", "fabricant", "type_molecule"])
    return f"MERGE (:Medicament {{canonical_id: {_esc(med['canonical_id'])}}}) " \
           f"ON CREATE SET {props.replace('canonical_id: ' + _esc(med['canonical_id']) + ', ', '')} " \
           f"ON MATCH SET {props.replace('canonical_id: ' + _esc(med['canonical_id']) + ', ', '')};"


def _merge_node(label: str, id_field: str, id_value: str, props: dict, prop_keys: list[str]) -> str:
    set_clause = ", ".join(f"n.{k} = {_esc(props.get(k))}" for k in prop_keys if k != id_field)
    if not set_clause:
        return f"MERGE (n:{label} {{{id_field}: {_esc(id_value)}}});"
    return (f"MERGE (n:{label} {{{id_field}: {_esc(id_value)}}}) "
            f"ON CREATE SET {set_clause} ON MATCH SET {set_clause};")


def convert_json(data: dict) -> list[str]:
    stmts: list[str] = []
    doc = data["document_info"]
    med = data["medicament"]

    stmts.append(_merge_node("Medicament", "canonical_id", med["canonical_id"], med,
                              ["nom", "dci", "fabricant", "type_molecule"]))

    for ev in data.get("evaluations", []):
        path = ev["pathologie"]
        stmts.append(_merge_node("Pathologie", "canonical_id", path["canonical_id"], path,
                                  ["nom", "icd10", "categorie", "severite"]))

        pop = ev.get("population")
        if pop:
            stmts.append(_merge_node("Population", "canonical_id", pop["canonical_id"], pop,
                                      ["profil_genetique", "sous_groupe", "gravite"]))

        eval_props = {
            "canonical_id": ev["canonical_id"],
            "smr_niveau": ev.get("smr_niveau"),
            "asmr_valeur": ev.get("asmr_valeur"),
            "asmr_signification": ev.get("asmr_signification"),
            "date_avis": ev.get("date_avis"),
            "date_avis_precision": ev.get("date_avis_precision"),
            "type_avis": ev.get("type_avis"),
            "ligne_traitement": ev.get("ligne_traitement"),
            "justification": ev.get("justification"),
            "document_id": doc["document_id"],
            "titre": doc.get("titre"),
        }
        stmts.append(_merge_node(
            "Evaluation", "canonical_id", ev["canonical_id"], eval_props,
            ["smr_niveau", "asmr_valeur", "asmr_signification", "date_avis",
             "date_avis_precision", "type_avis", "ligne_traitement", "justification",
             "document_id", "titre"]))

        stmts.append(
            f"MATCH (e:Evaluation {{canonical_id: {_esc(ev['canonical_id'])}}}), "
            f"(m:Medicament {{canonical_id: {_esc(med['canonical_id'])}}}) "
            f"MERGE (e)-[:CONCERNE]->(m);"
        )
        stmts.append(
            f"MATCH (e:Evaluation {{canonical_id: {_esc(ev['canonical_id'])}}}), "
            f"(p:Pathologie {{canonical_id: {_esc(path['canonical_id'])}}}) "
            f"MERGE (e)-[:POUR_INDICATION]->(p);"
        )
        if pop:
            stmts.append(
                f"MATCH (e:Evaluation {{canonical_id: {_esc(ev['canonical_id'])}}}), "
                f"(pp:Population {{canonical_id: {_esc(pop['canonical_id'])}}}) "
                f"MERGE (e)-[:SUR_POPULATION]->(pp);"
            )

        for arg in ev.get("arguments", []):
            # canonical_id derive de (categorie, orientation, type_argument) -- taxonomie
            # fermee, voir utils/arguments_taxonomy.py -- PAS du texte verbatim, qui varie
            # d'un document a l'autre pour le meme type d'argument. Le texte verbatim par
            # instance est porte par la relation INVOQUE, pas par l'identite du noeud.
            stmts.append(_merge_node("Argument", "canonical_id", arg["canonical_id"], arg,
                                      ["categorie", "orientation", "type_argument", "label"]))
            invoque_props = _props(arg, ["texte"])
            stmts.append(
                f"MATCH (e:Evaluation {{canonical_id: {_esc(ev['canonical_id'])}}}), "
                f"(a:Argument {{canonical_id: {_esc(arg['canonical_id'])}}}) "
                f"MERGE (e)-[r:INVOQUE]->(a) SET r += {{{invoque_props}}};"
            )

        for comp_entry in ev.get("comparateurs", []):
            comp = comp_entry["comparateur"]
            if not comp.get("canonical_id"):
                continue
            stmts.append(_merge_node("Comparateur", "canonical_id", comp["canonical_id"], comp,
                                      ["nom", "dci", "type_molecule"]))
            rel_props = _props(comp_entry, [
                "en_association_avec", "role", "endpoint_principal", "endpoint_secondaires",
                "resultat_principal", "resultat_secondaires", "evidence_excerpt"])
            stmts.append(
                f"MATCH (e:Evaluation {{canonical_id: {_esc(ev['canonical_id'])}}}), "
                f"(c:Comparateur {{canonical_id: {_esc(comp['canonical_id'])}}}) "
                f"MERGE (e)-[r:COMPARE_A]->(c) SET r += {{{rel_props}}};"
            )

    return stmts


CONSTRAINTS = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (m:Medicament) REQUIRE m.canonical_id IS UNIQUE;",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Pathologie) REQUIRE p.canonical_id IS UNIQUE;",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Comparateur) REQUIRE c.canonical_id IS UNIQUE;",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Evaluation) REQUIRE e.canonical_id IS UNIQUE;",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (pp:Population) REQUIRE pp.canonical_id IS UNIQUE;",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (a:Argument) REQUIRE a.canonical_id IS UNIQUE;",
]


def link_succede_a(all_data: list[dict]) -> list[str]:
    """Ordonne les Evaluation par (medicament, pathologie) sur date_avis croissante
    et relie chaque avis a son predecesseur direct. Trie sur la chaine ISO
    (YYYY-MM-DD / YYYY-MM / YYYY) : la comparaison lexicographique est valide
    tant que la precision est coherente (annee-mois-jour, zero-paddee)."""
    stmts: list[str] = []
    groups: dict[tuple[str, str], list[tuple[str, str]]] = {}

    for data in all_data:
        med_id = data["medicament"]["canonical_id"]
        for ev in data.get("evaluations", []):
            path_id = ev["pathologie"]["canonical_id"]
            date_avis = ev.get("date_avis")
            if not date_avis:
                continue
            groups.setdefault((med_id, path_id), []).append((date_avis, ev["canonical_id"]))

    ambiguous_same_date: list[str] = []
    for (med_id, path_id), entries in groups.items():
        entries.sort(key=lambda t: t[0])
        seen_dates = {}
        for date_avis, _ in entries:
            seen_dates[date_avis] = seen_dates.get(date_avis, 0) + 1
        for date_avis, count in seen_dates.items():
            if count > 1:
                ambiguous_same_date.append(f"{med_id}/{path_id}/{date_avis} ({count} avis)")

        for (prev_date, prev_id), (curr_date, curr_id) in zip(entries, entries[1:]):
            if prev_date == curr_date:
                # Meme date_avis -> jugements simultanes (ex: 2 sous-populations du meme
                # avis), pas une succession dans le temps. Pas d'arc, deja signale ci-dessus.
                continue
            stmts.append(
                f"MATCH (e1:Evaluation {{canonical_id: {_esc(curr_id)}}}), "
                f"(e2:Evaluation {{canonical_id: {_esc(prev_id)}}}) "
                f"MERGE (e1)-[:SUCCEDE_A]->(e2);"
            )

    if ambiguous_same_date:
        print("ATTENTION — plusieurs Evaluation du meme (medicament, pathologie) partagent "
              "exactement la meme date_avis (SUCCEDE_A non tranchable entre elles) :")
        for a in ambiguous_same_date:
            print(f"  - {a}")

    return stmts


def main(json_dir: str = "data/json", out_dir: str = "data/cypher"):
    json_dir_path = Path(json_dir)
    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)

    all_data = []
    for json_file in sorted(json_dir_path.glob("*.json")):
        with open(json_file, encoding="utf-8") as f:
            data = json.load(f)
        all_data.append(data)

        stmts = convert_json(data)
        out_path = out_dir_path / f"{json_file.stem}.cypher"
        out_path.write_text("\n".join(stmts) + "\n", encoding="utf-8")
        print(f"{json_file.name} -> {out_path.name} ({len(stmts)} statements)")

    succede_stmts = link_succede_a(all_data)
    succede_path = out_dir_path / "_succede_a.cypher"
    succede_path.write_text("\n".join(succede_stmts) + "\n", encoding="utf-8")
    print(f"\nSUCCEDE_A -> {succede_path.name} ({len(succede_stmts)} relations)")

    constraints_path = out_dir_path / "_constraints.cypher"
    constraints_path.write_text("\n".join(CONSTRAINTS) + "\n", encoding="utf-8")
    print(f"Contraintes -> {constraints_path.name}")


if __name__ == "__main__":
    json_dir_arg = sys.argv[1] if len(sys.argv) > 1 else "data/json"
    out_dir_arg = sys.argv[2] if len(sys.argv) > 2 else "data/cypher"
    main(json_dir_arg, out_dir_arg)
