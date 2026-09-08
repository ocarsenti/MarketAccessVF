"""3 requetes metier illustrant l'usage vise du graphe (voir docs/rapport_final.md
§7 pour l'analyse des resultats sur le corpus de test a 3 documents).

Q1 — avant de rediger l'argumentaire : quels arguments ont deja permis d'obtenir
     une ASMR I/II/III sur un profil clinique comparable (meme pathologie,
     meme type de comparateur) ?
Q2 — anticiper les points faibles : agregation des arguments defavorables par
     type_argument (taxonomie fermee), pour un type de comparateur donne.
Q3 — comparer sa situation a un precedent proche : recherche par profil de
     population + pathologie, verdict complet du/des precedent(s) trouve(s).
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(override=True)

URI = os.getenv("NEO4J_URI", "bolt://localhost:7688")
USER = os.getenv("NEO4J_USER", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "changeme123")


# Q1 : parametrer pathologie_id / mot-cle comparateur / plage ASMR selon le dossier en preparation.
Q1 = """
MATCH (e:Evaluation)-[:CONCERNE]->(m:Medicament)
MATCH (e)-[:POUR_INDICATION]->(p:Pathologie {canonical_id: 'c34'})
MATCH (e)-[:COMPARE_A]->(c:Comparateur)
WHERE c.type_molecule =~ '(?i).*(taxane|cytotoxique|chimiotherapie|chimiothérapie).*'
  AND e.asmr_valeur IN ['I','II','III']
MATCH (e)-[:INVOQUE]->(a:Argument)
WHERE a.orientation = 'favorable'
RETURN m.nom AS medicament, e.asmr_valeur AS asmr, e.ligne_traitement AS ligne,
       c.nom AS comparateur_chimio, a.type_argument AS argument_type, a.label AS argument_label,
       e.document_id AS dossier_source
ORDER BY medicament, argument_type
"""

# Q1 bis : meme perimetre clinique sans le filtre ASMR -- utile pour comprendre
# un Q1 vide (ex: le mecanisme d'action recherche n'a pas encore de precedent
# a ASMR<=III, mais une autre classe therapeutique si).
Q1_ELARGIE = """
MATCH (e:Evaluation)-[:CONCERNE]->(m:Medicament)
MATCH (e)-[:POUR_INDICATION]->(p:Pathologie {canonical_id: 'c34'})
MATCH (e)-[:COMPARE_A]->(c:Comparateur)
WHERE c.type_molecule =~ '(?i).*(taxane|cytotoxique|chimiotherapie|chimiothérapie).*'
RETURN m.nom AS medicament, m.type_molecule AS mecanisme, e.asmr_valeur AS asmr,
       c.nom AS comparateur, e.document_id AS dossier_source
ORDER BY asmr
"""

Q2 = """
MATCH (e:Evaluation)-[:COMPARE_A]->(c:Comparateur)
WHERE c.type_molecule =~ '(?i).*(taxane|cytotoxique|chimiotherapie|chimiothérapie).*'
MATCH (e)-[r:INVOQUE]->(a:Argument)
WHERE a.orientation = 'defavorable'
RETURN a.categorie AS categorie, a.type_argument AS type_argument, a.label AS label,
       count(*) AS frequence, collect(DISTINCT e.document_id) AS dossiers
ORDER BY frequence DESC, categorie
"""

# Q3 : precedents partageant un profil de population comparable (ici : marqueur
# genetique contenant "ALK") sur la meme pathologie -- generalisable a d'autres
# marqueurs en changeant le motif de la regex.
Q3 = """
MATCH (e1:Evaluation)-[:SUR_POPULATION]->(pop1:Population)
MATCH (e1)-[:CONCERNE]->(m1:Medicament)
MATCH (e1)-[:POUR_INDICATION]->(p1:Pathologie)
WHERE pop1.profil_genetique =~ '(?i).*ALK.*'
MATCH (e2:Evaluation)-[:SUR_POPULATION]->(pop2:Population)
MATCH (e2)-[:CONCERNE]->(m2:Medicament)
WHERE pop2.profil_genetique =~ '(?i).*ALK.*' AND e1 <> e2 AND p1.canonical_id = (
  [(e2)-[:POUR_INDICATION]->(pp) | pp.canonical_id][0]
)
RETURN m1.nom AS medicament_1, e1.smr_niveau AS smr_1, e1.asmr_valeur AS asmr_1,
       m2.nom AS medicament_2, e2.smr_niveau AS smr_2, e2.asmr_valeur AS asmr_2,
       pop1.sous_groupe AS sous_groupe_1, pop2.sous_groupe AS sous_groupe_2
"""


def run(session, label: str, query: str):
    print(f"\n{'='*70}\n{label}\n{'='*70}")
    rows = [r.data() for r in session.run(query)]
    if not rows:
        print("(aucun resultat)")
    for row in rows:
        print(row)
    return rows


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    with driver.session() as session:
        run(session, "Q1 — arguments favorables ayant permis ASMR I/II/III (CBNPC, comparateur chimio)", Q1)
        run(session, "Q1 bis — meme perimetre, sans filtre ASMR (comprendre un Q1 vide)", Q1_ELARGIE)
        run(session, "Q2 — arguments defavorables les plus frequents vs comparateur chimio", Q2)
        run(session, "Q3 — precedents sur profil de population comparable (marqueur ALK)", Q3)
    driver.close()


if __name__ == "__main__":
    main()
