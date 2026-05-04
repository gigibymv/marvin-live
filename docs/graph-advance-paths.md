# Cartographie : chemins concurrents qui font avancer le graph

> But du document : identifier toutes les voies qui pilotent l'avancement de LangGraph pour une mission, repérer les courses, et désigner UN seul propriétaire. Pas de code dans ce document — uniquement la carte et la décision de design.
>
> Contexte : la mission `m-netflix-20260504-x-20beb7b0` s'est figée à `next=('research_join',)` malgré 5 tentatives de reprise. Logs : `Detached resume aborted — mission already locked` puis `Resume step limit reached`. Ce n'est pas le code de `research_join` qui est en cause — c'est la contention entre les chemins de reprise.

## 1 — La carte des chemins

Toute fonction qui peut faire avancer le graph (appeler `graph.astream`, livrer un `Command(resume=...)`, ou tenir le `mission_lock`).

| Nom | Fichier:ligne | Trigger | Tient lock ? | Appelle astream ? | Échec silencieux ? | Step limit |
|---|---|---|---|---|---|---|
| `_stream_chat` | `marvin_ui/server.py:1626–2032` | `POST /chat` (SSE long-poll) | **Oui** (timeout 5s) | Oui (direct) | Oui (log + SSE error) | Aucune (boucle infinie jusqu'au close) |
| `_stream_resume` | `server.py:2230–2592` | `GET /resume` (re-attache après gate) | **Oui** (timeout 5s) | Oui (direct) | Oui | **8 passes max** (`while resume_steps < 8`) |
| `_stream_resume_passive` | `server.py:2070–2199` | Fallback de `_stream_resume` quand un autre détient le lock | Non (lecture seule) | Non (listener) | Oui | N/A |
| `_drive_detached_resume` | `server.py:454–625` | Spawn par `_spawn_detached_resume` ou par recovery finally | **Oui** (timeout 5s) | Oui (direct) | Oui (log warnings) | **8 steps** (`for _step in range(8)`) |
| `_spawn_detached_resume` | `server.py:643–659` | Appelé depuis `validate_gate` ET depuis les `finally` de `_stream_chat` / `_stream_resume` | N/A | N/A (queue uniquement) | Oui | N/A |
| `validate_gate` | `server.py:3511–3756` | `POST /gates/{id}/validate` | Non (mais spawn détaché) | Non (livre via `_deliver_resume`) | Oui (warnings) | N/A |
| `gate_node` | `marvin/graph/gates.py:30–250` | Routé par `phase_router` quand `pending_gate_id` set | N/A | N/A (interrupt interne) | Non (3 retries `evaluate_gate_material`) | 3 retries de 1–2s |
| `gate_entry_node` | `runner.py:617` | Routé par `phase_router` | N/A | N/A | Non | N/A |

## 2 — Les courses observées

### Course A — Approve → Reconnect simultanés
1. `_stream_chat` tient le lock (le SSE initial est encore ouvert).
2. L'utilisateur approuve un gate → `validate_gate` essaie de livrer le payload via `_deliver_resume`.
3. Si la livraison rate (le SSE est mort entre-temps), `validate_gate` spawn un `_drive_detached_resume`.
4. Le frontend reconnecte → `_stream_resume` essaie d'acquérir le lock → timeout 5s → tombe sur `_stream_resume_passive` (lecture seule).
5. `_drive_detached_resume` épuise ses 8 steps avant que le graph atteigne le prochain interrupt → `Resume step limit reached`.
6. Le passive listener n'a rien à relayer puisque le driver détaché est mort.
**Symptôme : mission figée à `next=('research_join',)`, UI bloquée à 50%.**

### Course B — Recovery se chevauche avec un driver actif
1. `_stream_chat` se termine en exception (ex : socket fermé en plein resume).
2. Son `finally` tente de spawn un `_drive_detached_resume` avec `pending_recovery_payload`.
3. Mais `validate_gate` a déjà spawné un driver détaché.
4. `_spawn_detached_resume` voit qu'un driver tourne → met le payload dans `_queued_detached_resumes`.
5. Le driver actif finit ses 8 steps, lit la queue, spawn un nouveau driver pour le payload en attente.
6. Si ce 2e driver re-épuise 8 steps avant le prochain interrupt → orphelin.

### Course C — Material check synchrone shadowing les retries du graph
1. `gate_node` a une logique de retry 3× avec backoff (`gates.py:61–85`) pour absorber les races post-agent.
2. Mais `validate_gate` appelle `evaluate_gate_material` **avant** de spawn quoi que ce soit (`server.py:3618`).
3. Si du material manque transitoirement → 409 conflict côté HTTP → l'utilisateur voit une erreur, le driver détaché ne se lance pas.
4. Les retries de `gate_node` ne se déclenchent jamais.

## 3 — Le propriétaire unique recommandé

**`_stream_chat` (et `_stream_resume` comme fallback de reconnexion) sont les seuls qui doivent appeler `graph.astream`.**

Pourquoi :
- Tient la connexion SSE de l'utilisateur en main : peut émettre heartbeats, gérer les timeouts visibles, et faire remonter les exceptions au client.
- Boucle infinie naturelle (jusqu'au close du socket) → pas de limite artificielle.
- `astream` + `Command(resume=...)` séquentiels sur la même event loop → cohérence garantie.

**Les autres deviennent passifs ou disparaissent :**

| Chemin | Devient |
|---|---|
| `_stream_resume_passive` | Reste passif (déjà conforme) |
| `_drive_detached_resume` | **Demoted** : ne tourne QUE si aucun client n'est attaché ET qu'un payload de reprise est en attente. Pas de boucle 8-steps, pas de spawn auto par `validate_gate`. |
| `_spawn_detached_resume` (depuis `validate_gate`) | **Supprimé**. À la place, `validate_gate` met une "verdict pending" flag dans le store ; le prochain `/chat` ou `/resume` client la lit et drive le graph. |
| `_spawn_detached_resume` (depuis recovery `finally`) | **Supprimé**. Le client va reconnecter (`/resume`) et reprendre lui-même. |
| Step limit `while resume_steps < 8` dans `_stream_resume` | **Supprimé** ou monté à infinity. La limite naturelle est le timeout du socket utilisateur. |
| Retries 3× de `gate_node` | **Conservé** mais le `evaluate_gate_material` synchrone dans `validate_gate` est **supprimé** : on fait confiance au graph pour ré-évaluer. |

## 4 — Chemins morts à supprimer

1. **Le step limit 8 dans `_stream_resume` (`server.py:2458`)** — shadowé par le fallback passive (`server.py:2240–2247`). Si le lock est tenu, on tombe en passive avant d'entrer dans la boucle. La boucle n'est donc jamais exécutée pour le cas "active driver concurrent" — elle existe pour rien. Supprimer.

2. **Le spawn de recovery dans les `finally` de `_stream_chat` et `_stream_resume` (`server.py:2049–2067` et `~2604`)** — crée systématiquement la course B. La logique correcte : ne rien spawn ; le client reconnecte sur `/resume` et c'est lui qui drive.

3. **L'évaluation synchrone du material dans `validate_gate` (`server.py:3618–3638`)** — fait échouer en 409 ce que `gate_node` aurait absorbé via ses retries. Soit on déplace l'éval dans le driver, soit on la supprime et on laisse le graph trancher.

4. **`_queued_detached_resumes`** — utile uniquement à cause de la course B. Une fois B éliminée, la queue n'a plus de raison d'exister.

## 5 — Étapes concrètes (à valider avant tout commit)

Phase 1 — décisions à prendre **avec le user** (10 min) :
- [ ] Confirmer que `validate_gate` ne spawn plus de driver détaché (acceptable de demander au client de reconnecter ?)
- [ ] Confirmer suppression du step limit 8 (le timeout naturel du SSE long-poll suffit)
- [ ] Confirmer suppression de la queue `_queued_detached_resumes`
- [ ] Confirmer que `evaluate_gate_material` synchrone dans `validate_gate` est retiré

Phase 2 — implémentation (un seul commit, ≤ 100 lignes nettes) :
- [ ] `validate_gate` : retire le spawn détaché ; persiste juste le verdict + signale au prochain `/resume` qu'il y a un payload en attente
- [ ] `_stream_resume` : retire la fallback passive ET le step limit ; bloque jusqu'à acquisition du lock (ou socket close)
- [ ] `_stream_chat` / `_stream_resume` : retire le spawn de recovery dans les `finally`
- [ ] Supprime `_drive_detached_resume`, `_spawn_detached_resume`, `_queued_detached_resumes` si plus aucun appelant
- [ ] Supprime `_stream_resume_passive` si plus aucun appelant

Phase 3 — vérification :
- [ ] `make smoke`
- [ ] Tests : `test_phase_router`, `test_gate_material`, `test_gate_rejection_rerun`, `test_detached_resume_consumes_interrupt` (ce dernier sera obsolète, supprimer ou réécrire)
- [ ] Test live : créer une mission, approve un gate, fermer onglet pendant le resume, rouvrir → la reprise doit être idempotente et ne pas générer de course

## 6 — Ce que ce document n'est PAS

- Pas un patch. Aucun fichier ne change tant que le user n'a pas validé les décisions de Phase 1.
- Pas une réécriture du graph. La logique des nodes (research_join, gate_node, papyrus_*) reste intacte.
- Pas une suppression du AsyncSqliteSaver — le checkpointer reste, c'est juste les couches au-dessus qui se réduisent à une seule.
