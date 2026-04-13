# controle_domaine_tension.py — Contrôle de cohérence du domaine de tension

## Description

Vérifie que le `DomaineTension` de chaque câble électrique correspond à celui des
jonctions auxquelles il est connecté via le champ `cables_href` et la proximité
géométrique.

**Règle** : pour chaque câble possédant un `DomaineTension`, toutes les jonctions
liées (référençant ce câble et proches d'une extrémité) doivent avoir le même
domaine de tension que le câble.

## Fonctionnement

1. Chargement des câbles électriques (`RPD_CableElectrique_Reco.geojson`) et des
   jonctions (`RPD_Jonction_Reco.geojson`) depuis le répertoire d'entrée.
2. Pour chaque câble ayant un `DomaineTension` :
   - Recherche des jonctions liées (présentes dans `cables_href` **et** proches
     d'une extrémité du câble, ≤ seuil de distance).
   - Comparaison du `DomaineTension` du câble avec celui de chaque jonction liée.
3. Signalement des incohérences (tension câble ≠ tension jonction).

## Constantes

| Constante           | Valeur                             | Description                                      |
| ------------------- | ---------------------------------- | ------------------------------------------------ |
| `SEUIL_DISTANCE`    | 0.5 m (défini dans utilitaires)    | Distance max pour considérer un lien géométrique |
| `FICHIER_CABLES`    | `RPD_CableElectrique_Reco.geojson` | Fichier source des câbles électriques            |
| `FICHIER_JONCTIONS` | `RPD_Jonction_Reco.geojson`        | Fichier source des jonctions                     |

## Ligne de commande

```bash
python controle_domaine_tension.py --repertoire <chemin> [--sortie <chemin>]
```

| Argument       | Obligatoire | Description                                                                            |
| -------------- | ----------- | -------------------------------------------------------------------------------------- |
| `--repertoire` | Oui         | Répertoire contenant `RPD_CableElectrique_Reco.geojson` et `RPD_Jonction_Reco.geojson` |
| `--sortie`     | Non         | Répertoire de sortie (défaut : même que `--repertoire`)                                |

### Sorties

- `rapport_controle_domaine_tension.json` — rapport JSON synthétique du contrôle
- `ecarts_domaine_tension.geojson` — GeoJSON FeatureCollection des incohérences de tension

### Utilisation en tant que bibliothèque

```python
from controle_domaine_tension import controler_domaine_tension, executer_controle_cli

# Logique métier seule
resultats = controler_domaine_tension(cables, features_jonctions)

# Contrôle complet avec écriture des fichiers
resultat = executer_controle_cli(repertoire, sortie)
```
