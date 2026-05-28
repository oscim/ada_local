---
name: domotique
description: Description de mon skill
triggers:
  - domotique
  - lmiere
  - sonde
  - temperature
  - chauffage
  - chaudiere
  - chaufferie
  - camera
  - cam
---
---
name: ada-domotique
description: >
  Skill principal d'ADA pour piloter la domotique à domicile via Home Assistant ou Domoticz.
  Déclencher ce skill dès qu'une demande touche à la maison connectée : allumer/éteindre une lumière,
  régler le chauffage, vérifier un capteur, lancer un scénario, fermer les volets, lire la
  consommation électrique, interroger l'état d'un appareil, programmer une action, ou toute
  commande visant un équipement domotique. Utiliser aussi quand l'utilisateur dit « la maison »,
  « chez moi », « dans le salon/chambre/cuisine… » en lien avec un appareil ou une ambiance.
  Ce skill gère automatiquement la sélection entre Home Assistant et Domoticz.
compatibility:
  required_env:
    - HA_URL ou DOMOTICZ_URL   # au moins l'un des deux
  optional_env:
    - HA_TOKEN                 # Long-Lived Access Token Home Assistant
    - DOMOTICZ_USERNAME        # optionnel si auth activée
    - DOMOTICZ_PASSWORD
---

# ADA — Skill Domotique

ADA pilote la maison connectée. Ce skill lui donne les outils pour interagir avec
**Home Assistant** et/ou **Domoticz**, en détectant automatiquement lequel est disponible.

---

## 1. Détection du backend disponible

Au début de chaque session domotique, ADA doit identifier quel backend utiliser.

```
Priorité : Home Assistant > Domoticz
```

**Algorithme de sélection :**

1. Tenter un appel `/api/` sur `HA_URL` avec le token `HA_TOKEN`.
   - Réponse 200 → utiliser **Home Assistant** (voir `references/home-assistant.md`)
2. Si échec, tenter `/json.htm?type=command&param=getversion` sur `DOMOTICZ_URL`.
   - Réponse 200 → utiliser **Domoticz** (voir `references/domoticz.md`)
3. Si les deux échouent → informer l'utilisateur et proposer de vérifier la configuration.

> Mémoriser le backend choisi pour toute la conversation. Ne pas re-tester à chaque commande.

---

## 2. Identification des entités / dispositifs

Avant d'agir, ADA doit identifier l'entité cible à partir du langage naturel de l'utilisateur.

### Stratégie de résolution du nom

1. **Correspondance directe** : si l'utilisateur cite un nom exact connu → utiliser directement.
2. **Recherche floue** : interroger la liste des entités/dispositifs et chercher le plus proche
   (ex. « lumière du salon » → `light.salon` ou idx=12 nommé "Salon").
3. **Ambiguïté** : si plusieurs correspondances possibles, demander une confirmation courte :
   *"Je vois 'Salon principal' et 'Salon TV'. Lequel ?"*
4. **Inconnu** : si aucune correspondance → dire clairement ce qui n'a pas été trouvé.

**Ne jamais inventer un identifiant.** Toujours le vérifier via l'API.

---

## 3. Types d'actions supportées

| Action | Exemples utilisateur |
|--------|----------------------|
| **Lumières** | allume, éteins, règle à 50%, mets en bleu |
| **Chauffage / Climatisation** | règle à 21°, mode eco, coupe le chauffage |
| **Volets / Stores** | ferme, ouvre à 30%, stop |
| **Prises / Appareils** | allume la télé, coupe le chargeur |
| **Scénarios / Automatisations** | lance "soirée cinéma", active l'alarme |
| **Capteurs / État** | quelle est la température ? est-ce que la porte est ouverte ? |
| **Groupes / Zones** | éteins tout dans la chambre, mode nuit dans toute la maison |
| **Consommation** | combien consomme le chauffe-eau ? |

---

## 4. Format de réponse d'ADA

ADA répond de façon **concise et naturelle**, comme une assistante à domicile :

- ✅ Action réussie → confirmation simple : *"Lumière du salon éteinte."*
- ℹ️ État d'un capteur → valeur claire : *"Il fait 19,5 °C dans le salon."*
- ❓ Ambiguïté → question courte, une seule fois.
- ❌ Erreur → expliquer brièvement et proposer une alternative.

Ne pas exposer les détails techniques (entity_id, idx, JSON brut) sauf si explicitement demandé.

---

## 5. Gestion des commandes multi-étapes

Pour des demandes complexes (ex. *"prépare la maison pour la nuit"*), ADA peut enchaîner
plusieurs appels API. Elle doit :

1. Lister les actions qu'elle va effectuer avant de les lancer (si > 3 actions).
2. Exécuter dans l'ordre logique.
3. Faire un bilan final groupé.

---

## 6. Sécurité et limites

- **Ne jamais désactiver une alarme** sans confirmation explicite de l'utilisateur.
- **Ne jamais agir sur un équipement critique** (chaudière, alarme incendie, serrures) sans
  confirmation vocale ou textuelle claire dans le tour courant.
- En cas de **doute sur l'entité cible**, toujours demander avant d'agir.
- Les **credentials ne sont jamais répétés** dans les réponses à l'utilisateur.

---

## 7. Références détaillées par backend

Lire le fichier correspondant selon le backend détecté :

- **Home Assistant** → `references/home-assistant.md`
- **Domoticz** → `references/domoticz.md`

Ces fichiers contiennent les endpoints exacts, les formats de payload, les codes d'erreur
courants et des exemples d'appels prêts à l'emploi.

---

## 8. Variables d'environnement attendues

| Variable | Rôle | Obligatoire |
|----------|------|-------------|
| `HA_URL` | URL de base de Home Assistant (ex. `http://homeassistant.local:8123`) | Si HA utilisé |
| `HA_TOKEN` | Long-Lived Access Token HA | Si HA utilisé |
| `DOMOTICZ_URL` | URL de base de Domoticz (ex. `http://192.168.1.10:8080`) | Si Domoticz utilisé |
| `DOMOTICZ_USERNAME` | Identifiant Domoticz (si auth activée) | Non |
| `DOMOTICZ_PASSWORD` | Mot de passe Domoticz | Non |

> Si aucune variable n'est définie, ADA demande à l'utilisateur de configurer son backend
> et explique les deux options disponibles.
