# Rapport PDF des controles PLOR

## Description

Le script `rapport_pdf_plor.py` genere un rapport PDF de synthese a partir des resultats des controles PLOR. Il analyse les fichiers GeoJSON d'ecarts produits par les scripts de controle et construit un document PDF structuré avec :

- une synthese globale (nombre de controles, anomalies totales)
- un tableau recapitulatif par controle
- le detail des entites en ecart par type de controle

## Controles integres

| Fichier d'ecarts | Controle | Description |
| --- | --- | --- |
| `ecarts_plor_cable.geojson` | Superposition PLOR / cables | Points non superposes aux sommets des cables |
| `plor_doublons.geojson` | Doublons de points | Points leves en doublon geometrique (X, Y, Z) |
| `cheminement_superpose.geojson` | Superposition de cheminements | Cheminements partageant des segments geometriques |

## Usage CLI

```bash
python rapport_pdf_plor.py --repertoire <chemin> [--sortie <chemin>]
```

### Arguments

| Argument | Obligatoire | Description |
| --- | --- | --- |
| `--repertoire` | Oui | Repertoire contenant les fichiers GeoJSON d'ecarts |
| `--sortie` | Non | Repertoire de sortie (defaut : meme que l'entree) |

## Sortie

- **Fichier** : `rapport_controles_plor.pdf`
- **Format** : PDF A4, marges 2 cm, en-tetes fonces (#374151), lignes alternees

## Resultat CLI

Le script affiche un JSON :

```json
{
  "succes": true,
  "chemin_pdf": "chemin/rapport_controles_plor.pdf",
  "controles_disponibles": 3,
  "nombre_total_anomalies": 6
}
```

## Fonctions principales

| Fonction | Role |
| --- | --- |
| `collecter_resultats_controles` | Charge les fichiers d'ecarts et collecte les statistiques |
| `generer_rapport_pdf` | Construit et ecrit le document PDF |
| `executer_rapport_cli` | Point d'entree pour l'appel programmatique |

## Comportement

- Les fichiers d'ecarts absents sont marques "Non execute" dans le rapport
- Un fichier d'ecarts vide (0 features) est considere comme controle OK
- Le rapport est toujours genere meme si aucun controle n'a ete execute
