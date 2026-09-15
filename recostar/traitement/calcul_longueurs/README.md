# Calcul des longueurs de câbles

Calcul des longueurs géographiques (3D) et électriques des câbles à partir de fichiers GeoJSON de récolement, avec génération d'un rapport PDF.

## Scripts

| Script | Rôle |
| --- | --- |
| `calcul_longueur.py` | Calcule les longueurs géographiques et électriques (corrections aux extrémités + correction aérienne) |
| `rapport_longueur.py` | Génère le rapport PDF récapitulatif à partir des résultats JSON |
| `pipeline.py` | **Point d'entrée unique** : enchaîne calcul + rapport en une seule commande |

## Utilisation

### Pipeline (recommandé)

```bash
# Sortie dans le même répertoire que les GeoJSON
python pipeline.py --chemin-geojson <répertoire_geojson>

# Sortie dans un répertoire dédié
python pipeline.py --chemin-geojson <répertoire_geojson> --chemin-sortie <répertoire_sortie>
```

### Scripts individuels

```bash
python calcul_longueur.py --chemin-projet <chemin>
python rapport_longueur.py --chemin-projet <chemin>
```

## Arguments

| Argument | Obligatoire | Description |
| --- | --- | --- |
| `--chemin-geojson` | oui (pipeline) | Répertoire contenant les fichiers GeoJSON |
| `--chemin-sortie` | non (pipeline) | Répertoire de sortie (défaut : répertoire d'entrée) |
| `--chemin-projet` | oui (scripts individuels) | Répertoire du projet (GeoJSON dans `recolement/`) |

## Fichiers produits

```text
<sortie>/rapport/resultats_longueurs.json
<sortie>/rapport/rapport_longueurs_cables.pdf
```

## Tests

```bash
python -m pytest tests/ -v
```
