# Audit de conformité ARET-MMU

## Méthode

Cet audit confronte le document d’architecture fourni — relu intégralement, lignes 1 à 1 010 — avec le serveur MCP, le schéma SQLite, les importeurs, les hooks, les adaptateurs d’oracles et les tests actuellement présents dans `aret-memory/`. Les statuts signifient : **conforme** pour une exigence opérationnelle couverte, **partiel** pour une capacité présente mais incomplète, et **écart** lorsqu’une exigence explicite n’est pas encore disponible.

| Domaine | Exigence d’architecture | État initial | Éléments observés |
|---|---|---|---|
| Stockage | SQLite est la source canonique ; les vues sont dérivées | **Conforme** | `MemoryStore`, migrations, FTS5 reconstructible, exports dérivés. |
| Contexte | Pas de mémoire sémantique ni de résumé LLM autoritatif | **Conforme** | FIND/READ séparés, aucun embedding ni RAG. |
| Adressage | Identifiants `ARET://` stables | **Conforme** | Adresses knowledge, component, function, brick, proof et front. |
| Pagination | READ exact et READ_BATCH borné | **Conforme** | Bornes d’items et d’octets ; tests de dépassement. |
| Typage | Types et statuts épistémiques définis | **Conforme** | RULE, ARCHITECTURE, DECISION, FORENSIC, OBSERVATION, HYPOTHESIS, STATE, MEASUREMENT, DISCOVERY et statuts associés. |
| Preuve | `PROVEN` exige un PASS admissible lié | **Conforme** | Reçus HMAC, `proof_link`, trigger SQL et validation serveur. |
| Artefacts | Logs lourds externes avec hash | **Conforme** | `artifacts/`, vérification SHA-256, lecture bornée. |
| Oracles | Capture difftest/Wine/winediff/funcdiff | **Conforme** | Adaptateurs réels fermés pour difftest, `winehash`, winediff et funcdiff. `winehash` produit une mesure `UNKNOWN` comparable au runner Windows, sans usurper un verdict PASS. L’exécution Windows CI demeure naturellement dépendante de son environnement. |
| Écriture | Append-first, auditée et transactionnelle | **Conforme** | Ajout, versionnement, relations, Front et preuves produisent des audits. |
| Invalidation | Une preuve invalidée entraîne une réévaluation de statut selon politique | **Conforme** | `aret_invalidate_proof` retire l’admissibilité, audite l’action et rétrograde à `OBSERVED` tout `PROVEN` sans autre PASS admissible. |
| Relations | Liens explicites et historisés | **Conforme** | Relations append-only et auditées ; `aret_supersede_relation` crée le lien remplaçant et inscrit la chaîne de remplacement dans un événement `SUPERSEDE_RELATION` immuable. |
| Active Front | Front minimal, corrigeable ou reconstructible | **Conforme** | Lecture, mise à jour manuelle et `aret_rebuild_front` complètent les pointeurs dérivés sans effacer les clés manuelles. |
| Migration | 70/71/80/81 et historique avec provenance et contrôles | **Partiel** | 70/71/80/81, 82 et 90 migrés. La vue `aret_export_reference_91` est reconstruite depuis les objets canoniques ; l’importeur contrôlé `migration/import_doc91.py` attend sans invention le Markdown historique absent. |
| Exports | JSON, Markdown, HTML et vues de revue | **Conforme** | JSON, Markdown, HTML autonome échappé et bundles sont dérivés depuis le snapshot canonique. |
| Bundle | Manifest auto-décrit, hashes, artefacts, import vérifié | **Conforme** | Bundle v3 avec hash logique, hash de snapshot, inventaire d’artefacts, `source_device_id`, version de schéma et migrations hashées incluses. |
| Transfert | Import idempotent, aucune fusion SQLite vivante | **Conforme** | Import vers cible vide, bundle connu idempotent, fusion refusée. |
| Git | Namespace mémoire seul, conflits refusés, politique `auto_push=false` | **Conforme** | `status`/`commit`/`push` et l’auto-sync optionnel sont bornés à `.aret-memory/`. `sync_policy.json` désactive `auto_commit` et `auto_push` par défaut ; tout changement hors périmètre fait échouer l’auto-sync après le commit SQLite, sans annuler celui-ci. |
| Hooks | SessionStart restaure via `additionalContext`; Pre/PostCompact traçables | **Conforme** | `restore()` et l’enveloppe SessionStart officielle sont implémentés ; les hooks ARET-MMU sont installés dans `.claude/settings.json` et les checkpoints Pre/PostCompact sont auditables sur activation explicite. |
| MCP | Façade métier sans SQL libre | **Conforme** | 28 outils métier déterministes ; aucun SQL arbitraire exposé. |
| Sécurité | Pas de suppression/réécriture historique ni commit MCP implicite | **Conforme** | API append-first, Git externe et explicitement confirmé. |
| Tests | Mémoire, pagination, preuve, reprise, transfert et corruption | **Partiel** | Tests de base, bundle, oracles, invalidation, restauration, Front et checkpoints sont présents ; un test sur deux environnements ARET réels et un conflit Git distant restent à exécuter. |
| UI humaine | CLI, HTML et éventuellement graphe/timeline | **Partiel** | CLI, exports JSON/Markdown/HTML disponibles ; graphe et timeline restent facultatifs et non implémentés. |

## Corrections réalisées dans cette passe

Les écarts déterministes ont été corrigés. Le Memory Store offre désormais `restore()` et `aret_restore`; `SessionStart` renvoie l’enveloppe `hookSpecificOutput.additionalContext` attendue par Claude Code; les checkpoints de compaction sont auditables sur activation explicite; l’invalidation de preuve réévalue transactionnellement les connaissances `PROVEN`; le Front possède une reconstruction prudente; l’export HTML est dérivé du snapshot; et le Memory Bundle v3 contient l’inventaire hashé des migrations ainsi qu’une identité de source. Cette passe ajoute aussi l’auto-sync Git strictement borné et opt-in après commit SQLite, la supersession append-only de relations, la mesure Wine `winehash`, ainsi que la vue de synthèse dérivée compatible avec l’ancien numéro 91 et son statut non applicable à tout import.

## Écarts conditionnels restant assumés

Aucun écart fonctionnel ne concerne le document 91 : il est confirmé comme une synthèse redondante des sources déjà migrées et ne doit pas être importé. `aret_export_reference_91` reste une vue dérivée de compatibilité ; `migration/import_doc91.py` retourne `NOT_APPLICABLE`. La collecte sur un runner CI Windows/Wine heavy reste, par nature, conditionnée par la disponibilité de cet environnement ; les adaptateurs de capture et de preuve sont eux déjà intégrés.

## Référence

[1]: architecture/ARET-MMU_Architecture_Document_Definitif_v5_final.md "ARET-MMU — Architecture définitive, version v5"
