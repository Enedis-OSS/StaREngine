# controle_extremites.py — Contrôle des extrémités des câbles

## Description

Vérifie que chaque extrémité (départ et arrivée) de chaque câble électrique est liée
à au moins une entité du réseau : **jonction**, **support**, **coffret** ou
**poste électrique**.

**Règle** : une extrémité est considérée liée si au moins une entité remplit les
critères suivants :

- Pour les **jonctions** et **supports** : le câble est référencé dans le champ
  `cables_href` de l'entité **et** l'entité est à proximité géométrique (≤ seuil).
- Pour les **coffrets** : seule la proximité géométrique est vérifiée (pas de
  champ `cables_href`).
- Pour les **postes électriques** : seul le champ `cables_href` est vérifié (pas de
  contrainte de proximité, car le point de référence d'un poste ne coïncide pas
  avec les extrémités des câbles — structure de grande emprise).

## Fonctionnement

1. Chargement des câbles électriques (`RPD_CableElectrique_Reco.geojson`)
   depuis le répertoire d'entrée.
2. Chargement des collections de nœuds (`RPD_Jonction_Reco.geojson`,
   `RPD_Support_Reco.geojson`), des coffrets (`RPD_Coffret_Reco.geojson`)
   et des postes électriques (`RPD_PosteElectrique_Reco.geojson`).
3. Pour chaque câble LineString valide :
   - Extraction des coordonnées de la première et dernière extrémité.
   - Recherche des nœuds liés via `cables_href` + proximité.
   - Recherche des coffrets proches par proximité uniquement.
   - Recherche des postes électriques liés via `cables_href` uniquement.
   - Validation : l'extrémité est valide si au moins une entité est trouvée.

## Constantes

| Constante        | Valeur                          | Description                                      |
| ---------------- | ------------------------------- | ------------------------------------------------ |
| `SEUIL_DISTANCE` | 0.5 m                           | Distance max pour considérer un lien géométrique |

### Fichiers GeoJSON utilisés

| Fichier                            | Rôle                  | Critère de liaison          |
| ---------------------------------- | --------------------- | --------------------------- |
| `RPD_CableElectrique_Reco.geojson` | Câbles à contrôler    | —                           |
| `RPD_Jonction_Reco.geojson`        | Nœuds jonction        | `cables_href` + proximité   |
| `RPD_Support_Reco.geojson`         | Nœuds support         | `cables_href` + proximité   |
| `RPD_Coffret_Reco.geojson`         | Coffrets              | Proximité uniquement        |
| `RPD_PosteElectrique_Reco.geojson` | Postes électriques    | `cables_href` uniquement    |

## Ligne de commande

```bash
python controle_extremites.py --repertoire <chemin> [--sortie <chemin>]
```

| Argument       | Obligatoire | Description                                             |
| -------------- | ----------- | ------------------------------------------------------- |
| `--repertoire` | Oui         | Répertoire contenant `RPD_CableElectrique_Reco.geojson` |
| `--sortie`     | Non         | Répertoire de sortie (défaut : même que `--repertoire`) |

### Sorties

- `rapport_controle_extremites.json` — rapport JSON synthétique du contrôle
- `ecarts_extremites.geojson` — GeoJSON FeatureCollection des extrémités non liées (Points)

### Utilisation en tant que bibliothèque

```python
from controle_extremites import controler_extremites, executer_controle_cli

# Logique métier seule
resultats = controler_extremites(cables, collections_noeuds, features_coffrets)

# Contrôle complet avec écriture des fichiers
resultat = executer_controle_cli(repertoire, sortie)
```
