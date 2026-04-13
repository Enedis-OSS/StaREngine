# controle_geometrie.py — Contrôle de géométrie des câbles

## Description

Vérifie que chaque câble électrique possède une géométrie valide.

**Règles** :

- La géométrie doit être présente.
- Le type doit être `LineString`.
- La polyligne doit contenir au moins **2 points** de coordonnées.

## Fonctionnement

1. Chargement des câbles électriques (`RPD_CableElectrique_Reco.geojson`) depuis
   le répertoire d'entrée.
2. Pour chaque câble :
   - Vérification de la présence de la géométrie.
   - Vérification du type (`LineString` attendu).
   - Vérification du nombre de coordonnées (≥ 2).
3. Chaque câble reçoit un statut `valide` ou une `erreur` descriptive.

## Erreurs détectées

| Erreur                                            | Cause                                  |
| ------------------------------------------------- | -------------------------------------- |
| `ID du cable manquant`                            | Identifiant absent dans les propriétés |
| `Geometrie absente`                               | Pas de champ `geometry`                |
| `Geometrie invalide (type X, attendu LineString)` | Type de géométrie incorrect            |
| `Geometrie invalide (moins de 2 points)`          | Polyligne avec 0 ou 1 point            |

## Ligne de commande

```bash
python controle_geometrie.py --repertoire <chemin> [--sortie <chemin>]
```

| Argument       | Obligatoire | Description                                             |
| -------------- | ----------- | ------------------------------------------------------- |
| `--repertoire` | Oui         | Répertoire contenant `RPD_CableElectrique_Reco.geojson` |
| `--sortie`     | Non         | Répertoire de sortie (défaut : même que `--repertoire`) |

### Sorties

- `rapport_controle_geometrie.json` — rapport JSON synthétique du contrôle
- `ecarts_geometrie.geojson` — GeoJSON FeatureCollection des câbles en erreur géométrique

### Utilisation en tant que bibliothèque

```python
from controle_geometrie import valider_geometrie_cable, controler_geometrie, executer_controle_cli

# Validation d'un câble individuel
resultat = valider_geometrie_cable(cable)

# Logique métier seule
resultats = controler_geometrie(cables)

# Contrôle complet avec écriture des fichiers
resultat = executer_controle_cli(repertoire, sortie)
```
