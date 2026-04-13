# Rapport PDF des controles de projection

## Description

Le script `rapport_pdf_proj.py` genere un rapport PDF de synthese regroupant
les resultats de l'ensemble des controles de projection executes sur les
fichiers GeoJSON.

## Principe

Le rapport collecte les fichiers d'ecarts GeoJSON produits par chaque
controle et presente :

- une synthese globale (nombre de controles, anomalies totales)
- un tableau recapitulatif par controle avec le statut et le nombre d'anomalies
- le detail des entites en ecart avec leurs identifiants et metadonnees

## Controles integres

| Controle                | Fichier d'ecarts                   |
| ----------------------- | ---------------------------------- |
| Conformite CRS          | ecarts_proj.geojson                |
| Coherence ensemble      | ecart_proj_ensemble.geojson        |
| Coherence coordonnees   | ecarts_proj_coordonnees.geojson    |

## Colonnes de detail par controle

### Conformite CRS

| Colonne          | Description                               |
| ---------------- | ----------------------------------------- |
| ID entite        | Identifiant metier de l'entite            |
| Fichier source   | Nom du fichier GeoJSON d'origine          |
| CRS detecte      | Valeur brute du CRS trouve                |
| Type anomalie    | Type d'anomalie detectee                  |
| Priorite         | Niveau de priorite (`bloquant`)           |

### Coherence ensemble

| Colonne          | Description                               |
| ---------------- | ----------------------------------------- |
| ID entite        | Identifiant metier de l'entite            |
| Fichier source   | Nom du fichier GeoJSON d'origine          |
| CRS detecte      | CRS du fichier en ecart                   |
| CRS reference    | CRS de reference determine par vote       |
| Priorite         | Niveau de priorite (`bloquant`)           |

### Coherence coordonnees

| Colonne          | Description                               |
| ---------------- | ----------------------------------------- |
| ID entite        | Identifiant metier de l'entite            |
| Fichier source   | Nom du fichier GeoJSON d'origine          |
| Type geometrie   | Type de geometrie de l'entite             |
| Indice sommet    | Indice du sommet en ecart                 |
| Type anomalie    | Type d'anomalie detectee                  |
| Priorite         | Niveau de priorite (`bloquant`)           |

## Utilisation

### Parametres

| Parametre      | Obligatoire | Description                                |
| -------------- | ----------- | ------------------------------------------ |
| --repertoire   | Oui         | Repertoire contenant les fichiers d'ecarts |
| --sortie       | Non         | Repertoire de sortie pour le PDF           |

### Ligne de commande

```bash
python rapport_pdf_proj.py --repertoire <chemin> [--sortie <chemin>]
```

### Comportement par defaut

Si aucun repertoire de sortie n'est specifie, le PDF est genere dans le
repertoire d'entree.

## Sortie

| Element          | Valeur                        |
| ---------------- | ----------------------------- |
| Fichier genere   | rapport_controles_proj.pdf    |
| Format           | PDF (A4)                      |

## Sortie JSON (stdout)

```json
{
  "succes": true,
  "chemin_pdf": "chemin/rapport_controles_proj.pdf",
  "controles_disponibles": 3,
  "nombre_total_anomalies": 12
}
```

## Dependances

- reportlab (generation PDF)

## Tests

```bash
python -m pytest test_rapport_pdf_proj.py -v
```
