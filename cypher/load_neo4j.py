"""Charge les fichiers .cypher generes par json_to_cypher.py dans Neo4j.

Ordre : contraintes -> un fichier par document (noeuds + relations) -> SUCCEDE_A
(qui doit venir en dernier puisqu'il relie des Evaluation deja creees).
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv(override=True)

URI = os.getenv("NEO4J_URI", "bolt://localhost:7688")
USER = os.getenv("NEO4J_USER", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "changeme123")


def _statements(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [s.strip() for s in text.split(";\n") if s.strip()]


def load_dir(cypher_dir: str = "data/cypher"):
    cypher_dir_path = Path(cypher_dir)
    constraints_file = cypher_dir_path / "_constraints.cypher"
    succede_file = cypher_dir_path / "_succede_a.cypher"
    doc_files = sorted(
        f for f in cypher_dir_path.glob("*.cypher")
        if f.name not in ("_constraints.cypher", "_succede_a.cypher")
    )

    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    with driver.session() as session:
        if constraints_file.exists():
            for stmt in _statements(constraints_file):
                session.run(stmt)
            print(f"Contraintes appliquees ({constraints_file.name})")

        total = 0
        for f in doc_files:
            stmts = _statements(f)
            for stmt in stmts:
                session.run(stmt)
            total += len(stmts)
            print(f"  {f.name} : {len(stmts)} statements charges")
        print(f"Total noeuds/relations (hors SUCCEDE_A) : {total} statements")

        if succede_file.exists():
            stmts = _statements(succede_file)
            for stmt in stmts:
                session.run(stmt)
            print(f"SUCCEDE_A : {len(stmts)} relations chargees")

    driver.close()


if __name__ == "__main__":
    load_dir(sys.argv[1] if len(sys.argv) > 1 else "data/cypher")
