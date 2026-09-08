"""Execute et affiche les 3 requetes de validation du schema (Tache 5)."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(override=True)

URI = os.getenv("NEO4J_URI", "bolt://localhost:7688")
USER = os.getenv("NEO4J_USER", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "changeme123")


Q1 = """
MATCH (e:Evaluation)-[:POUR_INDICATION]->(p:Pathologie)
MATCH (e)-[:CONCERNE]->(m:Medicament)
WHERE e.asmr_valeur IN ['III','IV','V']
RETURN m.nom AS medicament, p.nom AS pathologie, e.asmr_valeur AS asmr,
       e.date_avis AS date_avis, p.canonical_id AS pathologie_id
ORDER BY p.canonical_id, e.date_avis
"""

Q2 = """
MATCH (e:Evaluation)-[r:INVOQUE]->(a:Argument)
WHERE a.categorie = 'methodologie' AND a.orientation = 'defavorable'
RETURN a.type_argument AS type_argument, a.label AS label, count(*) AS frequence,
       collect(r.texte)[0..2] AS exemples_verbatim
ORDER BY frequence DESC, type_argument
LIMIT 25
"""

Q3 = """
MATCH path = (e1:Evaluation)-[:SUCCEDE_A*]->(e2:Evaluation)
MATCH (e1)-[:CONCERNE]->(m:Medicament)
MATCH (e1)-[:POUR_INDICATION]->(p:Pathologie)
RETURN m.nom AS medicament, p.nom AS pathologie, length(path) AS longueur_chaine,
       [n IN nodes(path) | n.date_avis] AS dates
ORDER BY longueur_chaine DESC
"""


def run_query(session, label: str, query: str):
    print(f"\n{'='*70}\n{label}\n{'='*70}")
    result = session.run(query)
    rows = [r.data() for r in result]
    if not rows:
        print("(aucun resultat)")
        return rows
    for row in rows:
        print(row)
    print(f"\n-> {len(rows)} ligne(s)")
    return rows


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    with driver.session() as session:
        r1 = run_query(session, "1. ASMR III/IV/V (tous medicaments/pathologies confondus)", Q1)
        r2 = run_query(session, "2. Arguments methodologiques defavorables les plus frequents", Q2)
        r3 = run_query(session, "3. Trajectoires SUCCEDE_A (medicament, pathologie dans le temps)", Q3)
    driver.close()
    return r1, r2, r3


if __name__ == "__main__":
    main()
