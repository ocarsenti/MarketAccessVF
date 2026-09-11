# Schéma du graphe — MarketAccessVF

Périmètre : avis de la **Commission de la Transparence** de la HAS
(médicaments, SMR/ASMR). Ne couvre pas la CNEDiMTS (dispositifs médicaux,
SA/ASA) — projet séparé.

## Nœuds

| Nœud | canonical_id | Propriétés |
|---|---|---|
| `Medicament` | DCI normalisée (`atezolizumab`) | `nom`, `dci`, `fabricant`, `type_molecule` |
| `Pathologie` | ICD10 normalisé (`c34`) ou `pathologie_inconnue_<slug>` si non résolu | `nom`, `icd10`, `categorie`, `severite`, `icd10_resolu_automatiquement` |
| `Comparateur` | DCI normalisée (même structure que `Medicament`) | `nom`, `dci`, `type_molecule` |
| `Evaluation` | hash déterministe (voir ci-dessous) | `smr_niveau`, `asmr_valeur`, `asmr_signification`, `date_avis`, `date_avis_precision`, `type_avis`, `ligne_traitement`, `justification`, `document_id`, `titre`, `population_cible_min`, `population_cible_max`, `population_cible_texte_brut`, `population_cible_source_type`, `population_cible_commentaire_commission` |
| `Population` | hash du contenu | `profil_genetique`, `sous_groupe`, `gravite` |
| `Argument` | hash de (`categorie`, `orientation`, `type_argument`) | `categorie` ∈ {methodologie, efficacite, securite, besoin_medical_non_couvert, autre}, `orientation` ∈ {favorable, defavorable}, `type_argument` (taxonomie fermée, voir `utils/arguments_taxonomy.py`), `label` (libellé FR lisible du type) |

`Evaluation` est le nœud de réification central : un même `Medicament` produit
autant de nœuds `Evaluation` distincts qu'il y a de couples
(indication × jugement de la commission), y compris **au sein d'un même
document** quand un avis statue sur plusieurs sous-populations avec des
SMR/ASMR différents (cas observé dans le corpus test : Tecentriq CBNPC,
sous-groupe EGFR+ vs sous-groupe ALK+, même document, même date, jugements
opposés — Important/IV vs Insuffisant/NA).

## Relations

```
(Evaluation)-[:CONCERNE]->(Medicament)
(Evaluation)-[:POUR_INDICATION]->(Pathologie)
(Evaluation)-[:SUR_POPULATION]->(Population)                 # absente si aucune info de population dans le PDF
(Evaluation)-[:INVOQUE {texte}]->(Argument)   # texte verbatim porte par l'instance, pas par le noeud
(Evaluation)-[:COMPARE_A {en_association_avec, role, endpoint_principal,
                          endpoint_secondaires, resultat_principal,
                          resultat_secondaires, evidence_excerpt}]->(Comparateur)
(Evaluation)-[:SUCCEDE_A]->(Evaluation)   # même medicament + même pathologie, trié par date_avis croissante
(Evaluation)-[:S_APPUIE_SUR {contexte: string}]->(Evaluation)   # cite un AUTRE avis HAS (médicament différent) comme source du calcul de population cible
```

### Population cible

La section "Population cible" d'un avis n'est pas systématique (absente par
exemple sur les avis d'accès précoce post-AMM) — tous les champs
`population_cible_*` restent `null` quand elle est absente, jamais inventés.
Le chiffre peut être une valeur unique (`population_cible_min ==
population_cible_max`) ou une fourchette issue d'une décomposition par
sous-catégories. `population_cible_texte_brut` conserve le paragraphe
verbatim pour ne rien perdre de ce que le LLM n'aurait pas structuré.
`population_cible_commentaire_commission` n'est rempli que si la Commission
exprime une vraie réserve sur son propre chiffre (ex: Dupixent —
"probablement sous-estimé") — jamais pour un exposé neutre du calcul.

`population_cible_source_type` ∈ {`etude_externe`, `avis_has_anterieur`,
`les_deux`, `non_precise`}. Quand la source inclut un ou plusieurs autres
avis HAS (ex: Mounjaro citant Victoza 2015 et Ozempic 2022), chaque
référence devient une relation `S_APPUIE_SUR` — distincte de `SUCCEDE_A`,
qui capture la trajectoire dans le temps d'un même médicament, alors que
`S_APPUIE_SUR` relie deux `Evaluation` de médicaments différents.

Si l'avis référencé n'est pas encore dans le graphe au moment de
l'extraction, un nœud `Evaluation` **placeholder** est créé
(`canonical_id` déterminé uniquement par `medicament_nom` + `annee`, voir
`utils/avis_references.py` — préfixe `eval_placeholder_`, jamais en
collision avec le `canonical_id` d'une vraie `Evaluation`), marqué
`est_placeholder: true`. Chaque référence est aussi loggée dans
`data/avis_references_a_verifier.json` pour réconciliation manuelle
ultérieure avec la vraie `Evaluation` une fois celle-ci extraite — même
mécanisme que `data/pathologies_a_verifier.json` /
`data/arguments_a_verifier.json`. Cette réconciliation n'est pas
automatique : le placeholder garde son propre `canonical_id` même après
extraction de l'avis réel, qui reçoit son `canonical_id` normal
(`evaluation_canonical_id`, dérivé de médicament/pathologie/population/
document/date).

`document_id` et `titre` (propriété `ISSUE_DE_DOCUMENT` de la proposition
initiale) sont restés des **propriétés de `Evaluation`**, pas une relation
vers un nœud `Document` séparé — conforme à la proposition, car le corpus
test ne présente aucun cas où plusieurs `Evaluation` de documents
différents devraient être reliées à un même nœud `Document` partagé (un
document HAS = un identifiant unique).

## Écarts par rapport au schéma cible proposé

1. **Pas de nœud `Document` séparé.** Justifié ci-dessus — ajoutable plus
   tard sans casser l'existant si un besoin de traçabilité multi-documents
   apparaît (ex: un même document réévalué avec un errata).
2. **`Evaluation.canonical_id` inclut `population_id`**, pas seulement
   `medicament_id + pathologie_id + date_avis` comme suggéré en exemple
   dans la consigne initiale. **Nécessaire** : le corpus test a immédiatement
   montré une collision sinon (deux sous-populations différentes, même
   médicament, même pathologie ICD10, même date, dans le même document —
   voir `data/json/CT-16457_*.json`).
3. **`Pathologie.categorie`** est renseignée par le LLM à partir du contexte
   (ex: "oncologie") quand déductible, pas un champ contrôlé strict — le
   dictionnaire ICD10 (`utils/pathologies.py`) est la seule source
   d'autorité pour `icd10`, jamais le LLM (voir `icd10_resolu_automatiquement`).
4. **`Argument.canonical_id` ne dépend pas de `texte`.** Détecté en cours de
   build sur le corpus test lui-même : avec un hash sur le texte verbatim
   (comme suggéré littéralement dans la consigne initiale — "texte, categorie,
   orientation"), deux formulations différentes du même argument
   méthodologique ("absence de comparateur direct" vs "pas de donnée
   comparative versus le traitement de référence") produisent deux nœuds
   `Argument` distincts, ce qui rend la requête de validation n°2 (fréquence
   des arguments méthodologiques défavorables) inutilisable — exactement le
   problème d'ontologie que l'ancien projet avait déjà rencontré. Fix : un
   champ `type_argument` choisi par le LLM dans une **taxonomie fermée**
   (`utils/arguments_taxonomy.py`, ~30 valeurs réparties par catégorie) porte
   l'identité du nœud ; le texte verbatim par instance est déplacé sur la
   relation `INVOQUE` (comme `evidence_excerpt` sur `COMPARE_A`). Toute
   valeur hors taxonomie (hallucination LLM, ou "autre" explicite) est
   ramenée à `"autre"` et loggée dans `data/arguments_a_verifier.json` pour
   extension manuelle — même mécanisme que pour les pathologies non reconnues.

## Conventions canonical_id

- `Medicament` / `Comparateur` : DCI en minuscules, underscores, sans accents.
- `Pathologie` : code ICD10 (résolu par dictionnaire — jamais par le LLM,
  voir `utils/pathologies.py::resolve_icd10`) ; sinon
  `pathologie_inconnue_<slug>` + entrée loggée dans
  `data/pathologies_a_verifier.json` pour extension manuelle du dictionnaire.
- `Evaluation` / `Population` / `Argument` : hash SHA1 tronqué du contenu
  normalisé (voir `utils/ids.py`) — déterministe, permet le `MERGE`
  idempotent entre plusieurs runs d'extraction/injection.

## Dates

`date_avis` est extraite au format ISO le plus précis disponible dans le
PDF (`YYYY-MM-DD` si le jour est donné, sinon `YYYY-MM`, sinon `YYYY` en
dernier recours). `date_avis_precision` enregistre le niveau réellement
obtenu. `SUCCEDE_A` est calculé en triant les `Evaluation` d'un même
(medicament, pathologie) par `date_avis` croissante — voir
`cypher/json_to_cypher.py::link_succede_a`, qui **signale explicitement**
tout couple (médicament, pathologie) où deux avis partagent exactement la
même `date_avis` (ordre alors indéterminable).
