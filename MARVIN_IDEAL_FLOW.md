# MARVIN: The Ideal End-To-End Flow

*Note: This document captures the ideal product vision and flow for the MARVIN CDD platform.*

## 1. Ouverture de mission

Tu arrives sur une mission vide.

Tu vois immédiatement:
- le client,
- la cible,
- la question d’IC / question d’investissement,
- l’état de la mission,
- les workstreams qui vont être lancés.

Dans le chat, MARVIN te demande le brief:
- thèse d’investissement,
- questions clés,
- docs éventuels,
- angle de mission.

Tu peux:
- coller un brief,
- uploader des documents,
- préciser des contraintes.

À ce stade, l’écran ne montre aucun faux progrès.
- Pas de gate tant qu’il n’y a rien à valider.
- Pas de deliverable tant qu’aucun artefact réel n’existe.

## 2. Framing initial

Une fois le brief envoyé, MARVIN entre dans une phase de framing.

**Ce que le système doit faire:**
- extraire la question d’investissement,
- identifier les workstreams utiles,
- générer les premières hypothèses testables,
- créer le plan de mission.

**Ce qui doit apparaître côté produit:**
- *Dans le chat*, MARVIN reformule la mission:
  - ce qu’il pense qu’il faut prouver ou réfuter,
  - quelles hypothèses seront testées,
  - comment le travail sera découpé.
- *Dans le centre*, la mission commence à se remplir:
  - brief synthétique,
  - hypothèses initiales,
  - plan de travail.
- *Dans les checkpoints*, on voit qu’un premier point de validation arrive.

Le premier artefact généré ici, si tout fonctionne bien, c’est un **engagement brief** utile:
- pas un stub,
- pas un doc vide,
- pas “No hypotheses yet”,
- mais une vraie note de cadrage.

## 3. Gate 1 — Hypothesis confirmation

Quand le framing est prêt, MARVIN demande une validation humaine.

**En état idéal:**
Le gate arrive dans le chat comme une vraie demande de revue, pas comme une popup qui te tombe dessus sans contexte.

Le gate doit te dire clairement:
- où on en est,
- quelles hypothèses ont été formulées,
- ce que tu valides exactement,
- ce qui se passera si tu approuves,
- ce qui se passera si tu rejettes.

**Si tu approuves:**
MARVIN lance les workstreams de recherche.

**Si tu rejettes:**
MARVIN repart en framing, révise les hypothèses, te repropose une version propre.

**Si tu veux réfléchir plus tard:**
- la mission se met proprement en pause,
- un rappel persistant reste visible,
- tu peux revenir et rouvrir le review.

## 4. Phase de recherche parallèle

Une fois les hypothèses validées, MARVIN lance les agents de recherche.

Dans l’état cible, chaque agent a un rôle clair :

### Dora
Travaille les sujets marché / compétition / positionnement / moat.
Elle doit produire:
- signaux marché,
- landscape concurrentiel,
- lecture qualitative du moat,
- premiers findings liés aux hypothèses.

### Calculus
Travaille la partie financière / QoE / unit economics / anomalies / concentration.
Elle doit produire:
- analyses quantitatives,
- lecture des chiffres disponibles,
- points d’attention financiers,
- findings financiers propres.

### Lector / Papyrus phase 0
Selon le moment, un agent documentaire produit les premiers artefacts:
- engagement brief,
- premières notes de travail,
- workstream reports intermédiaires.

## 5. Ce que l’utilisateur doit voir pendant cette recherche

Si tout fonctionnait bien, l’UI raconterait exactement ce qui se passe.

**Dans le chat**
Tu verrais MARVIN expliquer:
- quel agent travaille,
- quel finding important vient d’être établi,
- quand un milestone a été franchi,
- quand un deliverable a été produit.
*(Pas de JSON brut. Pas de payload technique. Des phrases lisibles.)*

**Dans le live rail / event feed**
Tu aurais un signal compact:
- Dora active,
- finding ajouté,
- milestone livré,
- gate pending,
- deliverable ready.
*(Le rail signale. Le chat explique.)*

**Dans le centre**
Chaque onglet montrerait le contenu réel du workstream:
- Competitive
- Market
- Financial
- Risk
- Memo
*(Et ce contenu serait : distinct par onglet, relié à de vrais findings, non dupliqué, non vide.)*

**Dans les checkpoints**
Tu verrais l’avancement réel:
- hypothèses confirmées,
- recherche en cours,
- manager review en attente,
- red-team à venir,
- final review à venir.

**Dans les agents**
Tu verrais:
- quels agents sont en train de travailler,
- combien de milestones ils ont livrés,
- où ils en sont.

**Dans les deliverables**
Tu verrais apparaître:
- engagement brief,
- workstream reports,
- report final,
- executive summary,
- data book,
*(et ils seraient ouvrables, avec du contenu utile.)*

## 6. Gate 2 — Manager review (G1)

Quand la phase de recherche initiale est terminée, MARVIN te demande un deuxième arbitrage.

Ce gate sert à répondre à une question simple:
*“Est-ce que la recherche initiale est suffisamment solide pour passer en red-team et en synthèse ?”*

Le gate doit te montrer:
- les principaux claims trouvés,
- les findings importants,
- les zones de faiblesse,
- ce qui a été couvert,
- ce qui reste fragile.

**Si tu approuves:**
Adversus démarre le red-team.

**Si tu rejettes:**
MARVIN reboucle vers la recherche, demande plus de travail sur les points faibles.

## 7. Phase red-team — Adversus

Adversus est l’agent qui attaque le dossier.

**Son travail:**
- challenger les hypothèses,
- construire des scénarios de risque,
- identifier le weakest link,
- tester la robustesse de la story.

**Concrètement, il doit produire:**
- findings contradictoires,
- angles empirical / logical / contextual,
- stress cases,
- PESTEL / Ansoff / weakness mapping si pertinent.

*En état cible, ce n’est pas du bruit. Ce n’est pas un dump de texte. C’est une vraie contre-thèse structurée.*

## 8. Phase de synthèse — Merlin

Merlin est l’agent de synthèse narrative et de décision.

**Son travail:**
- regarder ce que Dora, Calculus et Adversus ont produit,
- vérifier la cohérence,
- repérer les trous,
- décider si la story est assez solide pour être “ship”.

Il peut:
- demander un nouveau tour de challenge,
- ou conclure que la story tient.

**Le mécanisme idéal:**
Si la story est insuffisante, Merlin renvoie vers Adversus pour un retry borné (pas une boucle infinie, pas un comportement opaque).

À la fin, Merlin doit poser un verdict clair:
- ship / not ready,
- avec raisons explicites.

## 9. Gate 3 — Final review (G3)

Avant la livraison finale, MARVIN repasse par un dernier arbitrage humain.

Ce gate doit te permettre de valider:
- la qualité de la synthèse,
- le fait que la story est défendable,
- que les red flags ont été vus,
- que le dossier est prêt à être packagé.

Ce gate doit te montrer:
- la synthèse des claims,
- le weakest link,
- le verdict Merlin,
- les derniers risques ouverts,
- ce qui sera généré si tu approuves.

## 10. Livraison finale

Si G3 est approuvé, MARVIN génère les deliverables finaux.

En état cible, on obtient réellement:
- un report PDF cohérent,
- un executive summary utile,
- un data book ou annexes structurées,
- les workstream reports,
- le brief de mission propre.

Et surtout:
- ils sont téléchargeables,
- ils ne sont pas vides,
- ils ne répètent pas trois fois la même phrase,
- ils ne contiennent pas de placeholders,
- ils sont reliés aux hypothèses et aux findings.

## 11. Ce que “bon fonctionnement” veut dire vraiment

Si MARVIN fonctionnait comme prévu, il y aurait 5 propriétés non négociables.

1. **Vérité d’état**
Ce qui est affiché à l’écran correspond exactement à l’état réel de la mission.

2. **Qualité minimale des artefacts**
Aucun deliverable “ready” ne sort s’il est vide, contradictoire, ou trivialement mauvais.

3. **Gates justifiés**
Aucun gate n’apparaît sans matière réelle à valider.

4. **Live vraiment live**
Les agents, les findings, les milestones et les deliverables reflètent un travail réel, pas un faux replay ni un stub ambigu.

5. **Collaboration humain + agents**
L’humain ne micro-manage pas les tools. Il arbitre les hypothèses, challenge les claims, valide les décisions structurantes.

## 12. En une phrase

> Si tout marchait comme prévu, MARVIN serait une mission de conseil pilotée comme un vrai dossier de cabinet, où les agents produisent et challengent le travail, l’humain arbitre aux checkpoints, et l’interface montre en permanence une image fidèle, utile et crédible de la mission.
