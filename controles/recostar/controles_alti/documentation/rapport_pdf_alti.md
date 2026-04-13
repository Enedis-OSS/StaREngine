# Rapport PDF des controles altimetriques

## Description

Le script `rapport_pdf_alti.py` genere un rapport PDF de synthese regroupant
les resultats de l'ensemble des controles altimetriques executes sur les
fichiers GeoJSON.

## Principe

Le rapport collecte les fichiers d'ecarts GeoJSON produits par chaque
controle et presente :

- une synthese globale (nombre de controles, anomalies totales)
- un tableau detaille par controle avec le statut et le nombre d'anomalies

## Controles integres

| Controle                | Fichier d'ecarts                         |
| ----------------------- | ---------------------------------------- |
| Conformite 3D           | ecarts_3d.geojson                        |
| Coordonnees Z nulles    | ecarts_z_null.geojson                    |
| Altimetrie des sommets  | ecarts_controle_alti_sommets.geojson     |
| Altimetrie IGN          | ecarts_z_ign.geojson                     |

## Utilisation

### Parametres

| Parametre      | Obligatoire | Description                                  |
| -------------- | ----------- | -------------------------------------------- |
| --repertoire   | Oui         | Repertoire contenant les fichiers d'ecarts   |
| --sortie       | Non         | Repertoire de sortie pour le PDF             |

### Ligne de commande

```bash
python rapport_pdf_alti.py --repertoire <chemin> [--sortie <chemin>]
```

### Comportement par defaut

Si aucun repertoire de sortie n'est specifie, le PDF est genere dans le
repertoire d'entree.

## Sortie

| Element                        | Valeur                         |
| ------------------------------ | ------------------------------ |
| Fichier genere                 | rapport_controles_alti.pdf     |
| Format                         | PDF (A4)                       |

## Sortie JSON (stdout)

```json
{
  "succes": true,
  "chemin_pdf": "chemin/rapport_controles_alti.pdf",
  "controles_disponibles": 4,
  "nombre_total_anomalies": 12
}
```

## Dependances

- reportlab (generation PDF)

## Tests

```bash
python -m pytest test_rapport_pdf_alti.py -v
```
