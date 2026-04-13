# Pipeline complet RecoStaR (conversion V1.1)

## Role

Orchestre l'enchainement complet des traitements RecoStaR en s'appuyant sur les scripts de conversion V1.1 : conversion GML vers GeoJSON, controles qualite des donnees, puis reconversion en GML conforme.

## Etapes executees

| Etape | Description | Script source |
| ----- | ----------- | ------------- |
| 1 | Conversion GML vers GeoJSON | `conversion/recostar/conversion_V1_1/recostar_to_geojson.py` |
| 2a | Controles altimetriques | `controles/recostar/controles_alti/pipeline_controle_alti.py` |
| 2b | Controles des noeuds | `controles/recostar/controles_noeuds/pipeline_controle_noeud.py` |
| 2c | Controles PLOR | `controles/recostar/controles_plor/pipeline_controle_plor.py` |
| 2d | Controles de projection | `controles/recostar/controles_projections/pipeline_controle_proj.py` |
| 3 | Conversion GeoJSON vers GML | `conversion/recostar/conversion_V1_1/geojson_to_recostar.py` |

## Parametres

### Obligatoires

| Parametre | Description |
| --------- | ----------- |
| `--entree` | Chemin du fichier GML RecoStaR en entree |
| `--sortie-geojson` | Repertoire de sortie des fichiers GeoJSON |
| `--sortie-gml` | Chemin du fichier GML de sortie |

### Optionnels

| Parametre | Defaut | Description |
| --------- | ------ | ----------- |
| `--logiciel` | `LAZio` | Logiciel utilise pour la generation |
| `--producteur` | `TEST` | Producteur du recolement |
| `--responsable` | `TEST` | Responsable du recolement |
| `--nom` | `TEST` | Nom du reseau |
| `--srs` | auto | CRS force (ex: `EPSG:2154`) |

## Sortie

Le pipeline produit un JSON sur `stdout` contenant le resultat de chaque etape, le nombre total d'anomalies detectees et la duree d'execution.

## Exemple d'utilisation

```bash
python pipeline_recostar_complet_v1_1.py \
    --entree C:\data\recolement.gml \
    --sortie-geojson C:\data\geojson_output \
    --sortie-gml C:\data\resultat.gml \
    --producteur ENEDIS \
    --nom MonReseau
```
