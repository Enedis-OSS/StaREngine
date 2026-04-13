# Pipeline de controle des projections

## Description

Le script `pipeline_controle_proj.py` orchestre l'execution sequentielle de
l'ensemble des controles de projection puis genere un rapport PDF de synthese.
Il permet de lancer tous les controles en une seule commande.

## Controles enchaines

L'execution suit l'ordre suivant :

1. Conformite CRS (`controle_proj.py`)
2. Coherence ensemble (`controle_proj_ensemble.py`)
3. Coherence coordonnees (`controle_proj_coordonnees.py`)
4. Generation du rapport PDF (`rapport_pdf_proj.py`)

## Comportement

- Chaque controle est execute independamment
- Un echec de controle n'empeche pas l'execution des suivants
- Le rapport PDF est genere apres tous les controles
- Les resultats sont centralises dans un unique flux de sortie JSON

## Utilisation

### Parametres

| Parametre      | Obligatoire | Description                                |
| -------------- | ----------- | ------------------------------------------ |
| --repertoire   | Oui         | Repertoire contenant les fichiers GeoJSON  |
| --sortie       | Non         | Repertoire de sortie pour les resultats    |

### Ligne de commande

```bash
python pipeline_controle_proj.py --repertoire <chemin> [--sortie <chemin>]
```

### Comportement par defaut

Si aucun repertoire de sortie n'est specifie, les fichiers d'ecarts et le
rapport PDF sont generes dans le repertoire d'entree.

## Fichiers produits

| Fichier                          | Controle                |
| -------------------------------- | ----------------------- |
| ecarts_proj.geojson              | Conformite CRS          |
| ecart_proj_ensemble.geojson      | Coherence ensemble      |
| ecarts_proj_coordonnees.geojson  | Coherence coordonnees   |
| rapport_controles_proj.pdf       | Rapport de synthese     |

## Sortie JSON (stdout)

```json
{
  "succes": true,
  "controles": {
    "controle_proj": { "succes": true, "nombre_anomalies": 0 },
    "controle_proj_ensemble": { "succes": true, "nombre_anomalies": 2 },
    "controle_proj_coordonnees": { "succes": true, "nombre_anomalies": 5 }
  },
  "rapport": { "succes": true, "chemin_pdf": "rapport_controles_proj.pdf" },
  "nombre_anomalies_total": 7
}
```

## Dependances

- controle_proj
- controle_proj_ensemble
- controle_proj_coordonnees
- rapport_pdf_proj (reportlab)

## Tests

```bash
python -m pytest test_pipeline_controle_proj.py -v
```
