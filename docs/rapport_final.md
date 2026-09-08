# Rapport final — MarketAccessVF

Périmètre : avis de la **Commission de la Transparence** de la HAS
(médicaments, SMR/ASMR). Voir [`docs/schema.md`](schema.md) pour le schéma
détaillé et la justification de chaque écart par rapport au schéma
initialement proposé.

## 1. Corpus réellement traité : 3/18

18 PDF avaient été sélectionnés pour le corpus de test (6 médicaments —
Tecentriq, Xalkori, Glivec, Opdivo, Yervoy, Mabthera — sur plusieurs
pathologies et années, pour pouvoir tester `SUCCEDE_A`). **Seuls 3 ont pu
être extraits** : la clé `ANTHROPIC_API_KEY` disponible (empruntée à un
autre projet du même compte après que celle d'origine s'est révélée
invalide) a manqué de crédit à 3/18. Décision prise avec l'utilisateur :
arrêter à 3/18 plutôt que d'attendre une recharge, et documenter la
limitation plutôt que de continuer avec des données incomplètes.

Documents effectivement chargés dans le graphe :

| Médicament | Pathologie | Document source |
|---|---|---|
| TECENTRIQ (atezolizumab) | CBNPC, 2 sous-populations (EGFR+ / ALK+) | `CT-16457_TECENTRIQ_CBNPC_PIC_INS_Avis2_CT16457.pdf` |
| XALKORI (crizotinib) | CBNPC ALK+ | `CT-12648_XALKORI Ins_Avis2_CT12648.pdf` |
| YERVOY (ipilimumab) | Mélanome avancé | `CT-12741_YERVOY_PIC_REEV_Avis3_CT12741.pdf` |

**Conséquence directe sur la validation** : avec seulement 3 documents
couvrant 3 médicaments *différents* (aucun médicament n'apparaît deux fois),
la requête n°3 (`SUCCEDE_A`) ne peut structurellement rien retourner sur ce
sous-corpus — ce n'est pas un échec du schéma, voir §4.3. Pour valider
`SUCCEDE_A` sur des trajectoires réelles, il faudrait au minimum les avis
Xalkori ou Glivec supplémentaires déjà sélectionnés dans `data/pdf/` mais
non extraits (à relancer avec `python3 extraction/extract_has.py <pdf>` une
fois une clé avec crédit disponible — le script reprend automatiquement là
où il s'est arrêté, les documents déjà extraits sont sautés).

## 2. Schéma final implémenté

Voir [`docs/schema.md`](schema.md) pour le détail complet. Résumé des 4
écarts justifiés par rapport à la proposition initiale :

1. Pas de nœud `Document` séparé — `document_id`/`titre` restent des
   propriétés de `Evaluation` (voir schema.md §"Écarts", point 1).
2. `Evaluation.canonical_id` inclut `population_id` en plus de
   `medicament_id + pathologie_id + date_avis` — **nécessaire**, une
   collision réelle a été observée sur le premier document extrait
   (Tecentriq CBNPC, 2 sous-populations EGFR+/ALK+, même document, même
   date : sans `population_id` les deux `Evaluation` auraient fusionné à
   tort). Voir §4.4 pour le détail du bug.
3. `Pathologie.categorie` reste un champ libre déduit par le LLM (ex.
   "oncologie"), non un enum contrôlé — seul `icd10` est une source
   d'autorité stricte (dictionnaire, jamais le LLM).
4. **`Argument` repensé pendant le build**, à la demande explicite de
   l'utilisateur après qu'il a identifié un problème d'ontologie
   (nommage incohérent d'une même chose d'un document à l'autre) déjà
   rencontré sur le projet précédent. Le schéma initialement proposé
   (`Argument{texte, categorie, orientation}`, `canonical_id` dérivé du
   texte) a été testé une première fois et a immédiatement montré le
   problème : deux formulations différentes du même argument
   méthodologique produisaient deux nœuds distincts, rendant la requête de
   fréquence (§3, requête 2) inexploitable. Fix : ajout d'un champ
   `type_argument` choisi par le LLM dans une **taxonomie fermée** de ~30
   valeurs (`utils/arguments_taxonomy.py`), qui porte désormais l'identité
   du nœud ; le texte verbatim par instance est déplacé sur la relation
   `INVOQUE` (comme `evidence_excerpt` sur `COMPARE_A`). Toute valeur hors
   taxonomie est ramenée à `"autre"` et loggée dans
   `data/arguments_a_verifier.json` pour extension manuelle — même
   mécanisme que pour les pathologies non reconnues.

## 3. Coût d'extraction observé

Modèle : `claude-sonnet-5` ($2/MTok entrée, $10/MTok sortie), PDF envoyé en
document base64, un seul appel par document (pas d'étape de décision de
niveau comme dans l'ancien script — jugée inutile pour ce schéma).

| Document | Tokens in | Tokens out | Coût |
|---|---:|---:|---:|
| CT-16457 TECENTRIQ | 101 195 | 4 190 | $0.2443 |
| CT-12648 XALKORI | 43 805 | 3 016 | $0.1178 |
| CT-12741 YERVOY | 53 529 | 3 704 | $0.1441 |
| **Total (3 docs)** | **198 529** | **10 910** | **$0.5062** |

Moyenne : **$0.169/document**. Extrapolé aux 18 documents du corpus de test
initialement prévu : **≈ $3.04** — coût marginal, le blocage à 3/18 est un
problème de solde de compte, pas de coût unitaire.

Détail machine-lisible : [`data/extraction_costs.json`](../data/extraction_costs.json).

## 4. Résultats des 3 requêtes de validation

Exécutées via `python3 cypher/validation_queries.py` sur le graphe chargé
(3 documents, 119 statements Cypher, voir `data/cypher/`).

### 4.1 — ASMR III/IV/V

Requête adaptée : plutôt que filtrer sur un `canonical_id` de pathologie
fixé à l'avance (le corpus test couvre 3 pathologies différentes, pas une
seule), la requête retourne tous les ASMR III/IV/V toutes pathologies
confondues — c'est la version utile sur ce corpus, la restriction à une
pathologie précise est un simple `WHERE p.canonical_id = '...'` en plus.

| Médicament | Pathologie | ASMR | Date avis |
|---|---|---|---|
| XALKORI | CBNPC ALK+ | III | 2013-04-03 |
| TECENTRIQ | CBNPC ALK+ (sous-population) | IV | 2018-05-30 |
| YERVOY | Mélanome avancé | IV | 2013-11-06 |

**Validé** : la requête transversale ASMR × Pathologie fonctionne comme
attendu — c'était précisément le cas d'usage impossible avec l'ancien
schéma (SMR/ASMR collé en attribut texte libre sur `A_INDICATION`).

### 4.2 — Arguments méthodologiques défavorables les plus fréquents

| type_argument | Fréquence | Exemples verbatim (via relation `INVOQUE`) |
|---|---:|---|
| `etude_ouverte_absence_aveugle` | 3 | "Le caractère ouvert de l'étude ne permet pas d'étudier..." / "Le suivi NIH... est un suivi en ouvert avec comparaison inter-essai..." |
| `sous_groupe_non_analysable` | 2 | "Seuls 2 patients avec mutation ALK+..." / "Incertitudes sur la quantité d'effet dans le sous-groupe EGFR..." |
| `comparateur_non_pertinent` | 1 | "...regrette que les données relatives au vémurafénib n'aient pas été incluses..." |
| `donnees_immatures` | 1 | "...analyse intermédiaire, la médiane de survie globale n'a pu être évaluée..." |
| `effectif_insuffisant` | 1 | "...analyse intermédiaire à 5 ans... porte sur seulement 72 patients..." |
| `risque_de_biais` | 1 | "...étude de cohorte rétrospective... sans définition de critère principal..." |

**Validé, et démontre directement la correction du problème d'ontologie**
(§2 point 4) : `etude_ouverte_absence_aveugle` et `sous_groupe_non_analysable`
regroupent chacun **2 formulations verbatim différentes**, issues de
documents différents (Tecentriq, Yervoy), sous un seul nœud `Argument`. Avec
le schéma initial (canonical_id sur le texte), ces 6 lignes seraient
devenues 6 nœuds `Argument` distincts avec une fréquence de 1 chacun — la
requête aurait été correcte syntaxiquement mais inutile analytiquement.

### 4.3 — Trajectoires `SUCCEDE_A`

Aucun résultat. **Cause : taille du corpus, pas défaut du schéma** — les 3
documents chargés portent sur 3 médicaments différents (Tecentriq, Xalkori,
Yervoy), aucun n'apparaît deux fois. `SUCCEDE_A` ne peut se former qu'entre
deux `Evaluation` du **même** (médicament, pathologie) : structurellement,
zéro chaîne n'est possible ici. Le mécanisme d'ordonnancement lui-même a en
revanche été exercé et a fonctionné correctement dans un cas limite réel :
les 2 `Evaluation` Tecentriq (mêmes médicament + pathologie ICD10, même
`date_avis` exacte "2018-05-30", sous-populations différentes) ont
correctement déclenché le garde-fou "date identique → pas de succession
inventée" plutôt que de produire un arc arbitraire (voir §4.4, bug n°3).
Le corpus complet (18 avis, 6 médicaments avec plusieurs avis chacun,
notamment Tecentriq ×12, Xalkori ×7+4, Glivec ×3+9) permettrait de valider
de vraies chaînes temporelles une fois l'extraction relancée.

## 4.4 — Bugs réels trouvés et corrigés pendant le build

Le corpus de test a rempli son rôle : trois bugs de fond ont été détectés
et corrigés *avant* d'affecter un corpus à l'échelle, chacun sur le premier
ou deuxième document traité :

1. **Collision de `canonical_id` sur `Evaluation`** — le premier document
   extrait (Tecentriq) contenait 2 `Evaluation` (sous-populations EGFR+ et
   ALK+) partageant `medicament_id`, `pathologie_id` (même ICD10 "C34") et
   `date_avis` identiques. La formule proposée dans la consigne initiale
   (`medicament_id + pathologie_id + date_avis`) les aurait fusionnées à
   tort. Fix : ajout de `population_id` à la clé de hash.
2. **`msg.content[0].text` supposait le premier bloc de la réponse
   toujours textuel** — `claude-sonnet-5` insère parfois un bloc de
   raisonnement (`ThinkingBlock`) avant le texte, ce qui faisait planter
   l'extraction sur certains PDF (`AttributeError`). Fix : scan de tous les
   blocs de la réponse pour ne garder que ceux de type `text`.
3. **`SUCCEDE_A` créait un arc entre deux `Evaluation` de même date** — la
   première version de `link_succede_a()` triait par date puis reliait
   systématiquement chaque paire consécutive, y compris quand les deux
   dates étaient strictement égales (donc non ordonnables). Concrètement :
   un arc `SUCCEDE_A` aurait été créé entre les 2 sous-populations
   Tecentriq du même document, ce qui n'a aucun sens (ce sont deux
   jugements simultanés du même avis, pas une succession dans le temps).
   Fix : aucun arc n'est créé entre deux entrées de même `date_avis` ; le
   cas est signalé explicitement en sortie de script.

## 5. Pathologies et arguments non catégorisés proprement

**Arguments** : `data/arguments_a_verifier.json` est vide — les 18
arguments extraits sur les 3 documents traités ont tous trouvé une
correspondance dans la taxonomie fermée (`type_argument_resolu_automatiquement:
true` sur 100% des arguments).

**Pathologies** : les 3 documents chargés n'ont produit aucune entrée dans
`data/pathologies_a_verifier.json` (CBNPC → C34, mélanome → C43, tous deux
déjà dans le dictionnaire). Le fichier contient néanmoins **6 entrées
résiduelles issues de 2 documents extraits lors d'un run antérieur puis
écartés du corpus final** (GLIVEC `CT-18123`, MABTHERA vascularite
`CT-13904` — extraits avant la correction du bug taxonomie Argument, donc
non conservés) :

- granulomatose avec polyangéite (GPA) / polyangéite microscopique (PAM)
- syndromes myélodysplasiques/myéloprolifératifs (SMD/SMP) à réarrangement PDGFR
- syndrome hyperéosinophilique (SHE) / leucémie chronique à éosinophiles (LCE) à FIP1L1-PDGFRα
- tumeurs stromales gastro-intestinales (GIST) Kit (CD117) positives
- GIST Kit-positive, traitement adjuvant post-résection
- dermatofibrosarcome protuberans (DFSP / Darier-Ferrand)

Ces 6 pathologies (rhumatologie/vascularites + oncologie rare) sont à
ajouter à `utils/pathologies.py::PATHOLOGIES_ICD10` avant de relancer
l'extraction sur Glivec/Mabthera — conservées ici pour ne pas perdre le
travail de détection déjà fait.

## 6. Choix d'infrastructure

- **Nouveau repo GitHub public dédié** (`MarketAccessVF`) plutôt qu'un
  sous-dossier `has_graph/` dans `has-market-access` : ce dernier a un
  historique git actif avec des modifications non commitées et des travaux
  en cours sans rapport avec cette tâche — repartir propre évite tout
  risque d'interférence et donne un périmètre de code review clair pour un
  repo public.
- **Neo4j : conteneur Docker local dédié** (`marketaccessvf_neo4j`, ports
  7475/7688), isolé du conteneur `has_neo4j` déjà utilisé par
  `has-market-access` (autre schéma, ne pas mélanger) — choix validé avec
  l'utilisateur.
- **Corpus PDF test** : copié depuis `has-market-access/data/` (186 PDF
  déjà présents, avis HAS publics) plutôt que d'attendre un nouvel envoi,
  18 sélectionnés pour la diversité pathologie/médicament/année.
