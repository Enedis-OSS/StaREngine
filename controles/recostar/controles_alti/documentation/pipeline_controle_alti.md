# Pipeline de controle altimetrique

## Description

Le script `pipeline_controle_alti.py` orchestre l'execution sequentielle de
l'ensemble des controles altimetriques puis genere un rapport PDF de synthese.
Il permet de lancer tous les controles en une seule commande.

## Controles enchaines

L'execution suit l'ordre suivant :

1. Conformite 3D (`controle_3d.py`)
2. Coordonnees Z nulles (`controle_z_null.py`)
3. Altimetrie des sommets (`controle_alti_sommets.py`)
4. Altimetrie IGN (`controle_alti_ign.py`)
5. Generation du rapport PDF (`rapport_pdf_alti.py`)

## Comportement

- Chaque controle est execute independamment
- Un echec de controle n'empeche pas l'execution des suivants
- Le rapport PDF est genere apres tous les controles
- Les resultats sont centralises dans un unique flux de sortie JSON

## Utilisation

### Parametres

| Parametre      | Obligatoire | Description                                  |
| -------------- | ----------- | -------------------------------------------- |
| --repertoire   | Oui         | Repertoire contenant les fichiers GeoJSON    |
| --sortie       | Non         | Repertoire de sortie pour les resultats      |

### Ligne de commande

```bash
python pipeline_controle_alti.py --repertoire <chemin> [--sortie <chemin>]
```

### Comportement par defaut

Si aucun repertoire de sortie n'est specifie, les fichiers d'ecarts et le
rapport PDF sont generes dans le repertoire d'entree.

## Fichiers produits

| Fichier                              | Controle                 |
| ------------------------------------ | ------------------------ |
| ecarts_3d.geojson                    | Conformite 3D            |
| ecarts_z_null.geojson                | Coordonnees Z nulles     |
| ecarts_controle_alti_sommets.geojson | Altimetrie des sommets   |
| ecarts_z_ign.geojson                 | Altimetrie IGN           |
| rapport_controles_alti.pdf           | Rapport de synthese      |

## Sortie JSON (stdout)

```json
{
  "succes": true,
  "controles": {
    "controle_3d": { "succes": true, "nombre_anomalies": 3 },
    "controle_z_null": { "succes": true, "nombre_anomalies": 38 },
    "controle_alti_sommets": { "succes": true, "nombre_anomalies": 5 },
    "controle_alti_ign": { "succes": true, "nombre_anomalies": 0 }
  },
  "rapport": { "succes": true, "chemin_pdf": "rapport_controles_alti.pdf" },
  "nombre_anomalies_total": 46
}
```

## Dependances

- controle_3d
- controle_z_null
- controle_alti_sommets
- controle_alti_ign
- rapport_pdf_alti (reportlab)

## Tests

```bash
python -m pytest test_pipeline_controle_alti.py -v
```
