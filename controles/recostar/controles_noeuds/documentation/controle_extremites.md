# controle_extremites.py — Contrôle des extrémités des câbles

## Description

Vérifie que chaque extrémité (départ et arrivée) de chaque câble électrique est liée
à au moins une entité du réseau via la relation attributaire `cables_href`.

**Règle** : une extrémité est considérée liée si au moins un nœud du réseau référence
le câble dans son champ `cables_href`. Aucune notion de proximité géométrique n'est
utilisée, ce qui élimine les faux positifs liés aux positions spatiales.

## Types de nœuds vérifiés

Tous les types de nœuds porteurs de `cables_href` (relation `CableElectrique_NoeudReseau`) :

- Jonction
- CoupeCircuitAFusibles
- PointDeComptage
- PosteElectrique
- JeuBarres
- SupportModules
- OuvrageCollectifBranchement

## Fonctionnement

1. Chargement des câbles électriques (`RPD_CableElectrique_Reco.geojson`)
   depuis le répertoire d'entrée.
2. Chargement de toutes les collections de nœuds possédant `cables_href`.
3. Construction d'un index inversé `cable_id → liste d'entités liées`
   à partir des champs `cables_href` de chaque nœud.
4. Pour chaque câble LineString valide :
   - Extraction des coordonnées de la première et dernière extrémité.
   - Consultation de l'index pour vérifier si le câble est référencé.
   - Validation : l'extrémité est valide si au moins une entité est trouvée.

### Fichiers GeoJSON utilisés

| Fichier                                          | Rôle                  | Critère de liaison |
| ------------------------------------------------ | --------------------- | ------------------ |
| `RPD_CableElectrique_Reco.geojson`               | Câbles à contrôler    | —                  |
| `RPD_CoupeCircuitAFusibles_Reco.geojson`         | Coupe-circuits        | `cables_href`      |
| `RPD_JeuBarres_Reco.geojson`                     | Jeux de barres        | `cables_href`      |
| `RPD_Jonction_Reco.geojson`                      | Jonctions             | `cables_href`      |
| `RPD_OuvrageCollectifBranchement_Reco.geojson`   | Ouvrages collectifs   | `cables_href`      |
| `RPD_PointDeComptage_Reco.geojson`               | Points de comptage    | `cables_href`      |
| `RPD_PosteElectrique_Reco.geojson`               | Postes électriques    | `cables_href`      |
| `RPD_SupportModules_Reco.geojson`                | Supports modules      | `cables_href`      |

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
resultats = controler_extremites(cables, collections_noeuds)

# Contrôle complet avec écriture des fichiers
resultat = executer_controle_cli(repertoire, sortie)
```
