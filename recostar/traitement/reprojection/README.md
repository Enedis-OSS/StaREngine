# Reprojection des GML RecoStaR

Reprojette un fichier GML au format RecoStaR vers une projection de sortie, via PyProj.

La **projection d'entrée n'est pas demandée** : elle est lue dans le fichier lui-même.

## Détermination de la projection d'entrée

Le CRS figure à deux endroits dans un GML RecoStaR :

| Source | Priorité |
| --- | --- |
| `Metadata/SRS` | primaire — fait foi |
| `srsName` des géométries | repli, quand `Metadata/SRS` est absent |

Les deux formats d'identifiant sont acceptés : `EPSG:2154` et l'URN OGC `urn:ogc:def:crs:EPSG::2154`. La normalisation est celle du contrôle de projection (`normaliser_epsg`), partagée plutôt que redéfinie.

Une divergence entre le déclaré et les géométries, ou des géométries hétérogènes entre elles, n'interrompt pas le traitement : le fait est remonté dans `avertissements`.

## Altitude

Seules les coordonnées planimétriques sont transformées. **Le Z est reporté tel quel** : les altitudes RecoStaR sont en NGF, système altimétrique indépendant de la projection planimétrique retenue.

## Utilisation

```bash
# Sortie dérivée du nom d'entrée : recolement_epsg3947.gml
python reprojection_gml.py --chemin-gml recolement.gml --epsg-sortie EPSG:3947

# Sortie explicite
python reprojection_gml.py --chemin-gml recolement.gml --epsg-sortie EPSG:3947 \
    --chemin-sortie /tmp/recolement_cc47.gml
```

## Arguments

| Argument | Obligatoire | Description |
| --- | --- | --- |
| `--chemin-gml` | oui | Fichier GML RecoStaR à reprojeter |
| `--epsg-sortie` | oui | Projection de sortie (`EPSG:NNNN` ou URN OGC) |
| `--chemin-sortie` | non | Fichier produit (défaut : entrée suffixée par la projection) |

## Sortie

Le GML reprojeté, plus un compte rendu JSON sur la sortie standard :

```json
{"succes": true, "chemin_sortie": "...", "epsg_source": "EPSG:2154",
 "epsg_cible": "EPSG:3947", "nb_geometries": 21, "nb_positions": 47}
```

En cas d'échec, `succes` vaut `false`, `erreur` porte le motif, et celui-ci est également écrit sur la sortie d'erreur.

## Ce que le fichier produit conserve

- le commentaire d'en-tête du GML source ;
- les préfixes de namespace d'origine (`RecoStaR`, `gml`, `xlink`, `xsi`) ;
- toutes les entités, relations et références, inchangées.

Les `srsName` et le champ `Metadata/SRS` sont réalignés sur la projection de sortie, pour rester cohérents avec les coordonnées écrites.

## Précision

Les coordonnées sont écrites au millimètre pour un CRS projeté (3 décimales) et à 9 décimales pour un CRS géographique, où 3 décimales vaudraient une centaine de mètres.

Un aller-retour `EPSG:2154 → EPSG:3947 → EPSG:2154` restitue les coordonnées d'origine à moins d'un millimètre.

## Tests

```bash
python -m pytest tests/ -v
```
