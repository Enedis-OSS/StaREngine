# Fusion de GML RecoStaR

Fusionne deux fichiers GML au format RecoStaR en un seul, en alignant au passage leurs projections.

## Logique

1. Les deux fichiers sont lus.
2. La projection de chacun est **déduite de son contenu** (`Metadata/SRS`, à défaut les `srsName`) — elle n'est jamais demandée.
3. Les projections sont comparées :
   - **identiques** : fusion directe ;
   - **différentes** : le fichier qui s'écarte de la cible est reprojeté avant fusion.
4. La cible est celle passée à `--epsg-cible` ; **sans consigne, c'est la projection du premier fichier** qui fait référence.

Le moteur de reprojection est celui du traitement `reprojection`, partagé et non redéfini.

## Utilisation

```bash
# Cible implicite : la projection du premier GML
python fusion_gml.py --chemin-gml-1 chantier_a.gml --chemin-gml-2 chantier_b.gml

# Cible explicite : les deux fichiers sont alignés dessus
python fusion_gml.py --chemin-gml-1 chantier_a.gml --chemin-gml-2 chantier_b.gml \
    --epsg-cible EPSG:3947 --chemin-sortie chantier_complet.gml
```

## Arguments

| Argument | Obligatoire | Description |
| --- | --- | --- |
| `--chemin-gml-1` | oui | Premier GML ; sa projection sert de référence par défaut |
| `--chemin-gml-2` | oui | Second GML, reprojeté s'il s'écarte de la cible |
| `--epsg-cible` | non | Projection du fichier produit (`EPSG:NNNN` ou URN OGC) |
| `--chemin-sortie` | non | Fichier produit (défaut : premier GML suffixé `_fusion`) |

## Ce que la fusion résout

### Unicité des `gml:id`

Le format impose des identifiants uniques sur tout le fichier. Or deux exports du même outil en partagent systématiquement une partie : `Reseau`, et tous les identifiants de géométrie dérivés d'un compteur par type (`RPD_Support_Reco_1.geom0`). Sur un export réel, **22 identifiants sur 66 ne sont pas des UUID**.

Les identifiants du second fichier entrant en collision sont renommés en `id<uuid4>`, et les `xlink:href` qui les désignent suivent le renommage — sous leurs deux formes, référence directe et fragment local `#identifiant`.

Les références qui ne visent aucun `gml:id` (CodeLists : `NatureSupport="Poteau"`, `FonctionCable="DistributionEnergie"`) sont laissées intactes.

### Unicité du `Metadata`

Le modèle n'en admet qu'un par fichier : celui du second est écarté, et le fait est signalé dans `avertissements`.

Les `ReseauUtilite` sont en revanche **tous conservés** — le modèle en admet plusieurs, précisément pour les tranches de travaux, ce qu'est une fusion de deux chantiers.

### Versions de schéma

Deux fichiers déclarant des `schemaLocation` différents (V1.0 et V1.1) interrompent le traitement : les fusionner produirait un document incohérent.

## Sortie

```json
{"succes": true, "chemin_sortie": "...", "epsg_cible": "EPSG:2154",
 "epsg_sources": ["EPSG:2154", "EPSG:3947"], "nb_reprojetes": 1,
 "nb_entites_ajoutees": 44, "nb_ids_remappes": 66,
 "avertissements": ["Metadata du second fichier ecarte (1) : le modele n'en admet qu'un"]}
```

En cas d'échec, `succes` vaut `false` et `erreur` porte le motif, également écrit sur la sortie d'erreur.

## Limites

Aucune déduplication n'est effectuée : fusionner deux fichiers décrivant le même ouvrage produit deux entités distinctes, superposées. C'est une fusion, pas une consolidation.

## Tests

```bash
python -m pytest tests/ -v
```
