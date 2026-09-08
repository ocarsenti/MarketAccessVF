# MarketAccessVF

Pipeline d'extraction des avis de la **Commission de la Transparence** de la
HAS (médicaments — SMR/ASMR) vers un graphe Neo4j, avec un schéma qui réifie
explicitement l'évaluation par indication, la population étudiée et les
arguments favorables/défavorables — plutôt que de les coller en texte libre
sur une seule relation (voir [`docs/schema.md`](docs/schema.md) pour le détail
et la justification des écarts par rapport au schéma initialement proposé).

Reprend le principe (fonctionnel) d'un script d'extraction antérieur du
projet `has-market-access` : envoyer le PDF directement à Claude (`document`
content block), avec un prompt qui interdit toute complétion par
connaissances générales. La structure JSON de sortie et le graphe Neo4j sont
entièrement repensés ici.

> Périmètre : Commission de la Transparence (médicaments, SMR/ASMR)
> uniquement — ne couvre pas la CNEDiMTS (dispositifs médicaux, SA/ASA).

## Installation

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # puis renseigner ANTHROPIC_API_KEY

docker-compose up -d   # Neo4j dédié, ports 7475 (browser) / 7688 (bolt)
```

## Pipeline

```bash
# 1. Extraction PDF -> JSON (un fichier par avis)
python3 extraction/extract_has.py data/pdf/<avis>.pdf

# 2. JSON -> Cypher (idempotent, MERGE sur canonical_id)
python3 cypher/json_to_cypher.py

# 3. Chargement Neo4j
python3 cypher/load_neo4j.py

# 4. Requêtes de validation du schéma
python3 cypher/validation_queries.py
```

Neo4j Browser : http://localhost:7475 (auth `neo4j` / `changeme123`, voir
`.env.example`).

## Structure

```
extraction/extract_has.py    # PDF -> JSON structuré (API Anthropic, claude-sonnet-5)
utils/pathologies.py         # dictionnaire ICD10 + log des pathologies non reconnues
utils/arguments_taxonomy.py  # taxonomie fermée des types d'arguments + log des non reconnus
utils/ids.py                 # canonical_id déterministes (Evaluation/Population/Argument)
cypher/json_to_cypher.py     # JSON -> Cypher MERGE + calcul SUCCEDE_A
cypher/load_neo4j.py         # charge les .cypher dans Neo4j
cypher/validation_queries.py # les 3 requêtes de validation du schéma
cypher/exemples_metier.py    # 3 requêtes représentatives des cas d'usage réels (voir rapport §7)
data/pdf/                    # corpus de test (18 avis)
data/json/                   # sorties d'extraction
data/cypher/                 # Cypher généré
data/pathologies_a_verifier.json   # pathologies non résolues par le dictionnaire
data/arguments_a_verifier.json     # types d'arguments hors taxonomie fermée
data/extraction_costs.json         # coût observé par document (tokens/$ )
docs/schema.md                     # schéma détaillé + écarts justifiés
docs/rapport_final.md              # Tâche 6 : rapport de validation
```

## Coût d'extraction

Suivi automatiquement dans `data/extraction_costs.json` (tokens in/out et
coût par document, modèle `claude-sonnet-5`). Résumé dans
[`docs/rapport_final.md`](docs/rapport_final.md).
