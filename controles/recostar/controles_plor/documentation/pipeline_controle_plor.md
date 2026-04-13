# Pipeline de controle PLOR

## Description

Le script `pipeline_controle_plor.py` orchestre l'execution sequentielle de l'ensemble des controles PLOR puis genere un rapport PDF de synthese. Il permet de lancer tous les controles en une seule commande.

## Controles enchaines

| Ordre | Controle | Script |
| --- | --- | --- |
| 1 | Superposition PLOR / cables | `controle_plor_cable.py` |
| 2 | Doublons de points | `controle_plor_doublons.py` |
| 3 | Superposition de cheminements | `controle_cheminement_superpose.py` |
| 4 | Generation du rapport PDF | `rapport_pdf_plor.py` |

## Usage CLI

```bash
python pipeline_controle_plor.py --repertoire <chemin> [--sortie <chemin>]
```

### Arguments

| Argument | Obligatoire | Description |
| --- | --- | --- |
| `--repertoire` | Oui | Repertoire contenant les fichiers GeoJSON a analyser |
| `--sortie` | Non | Repertoire de sortie (defaut : meme que l'entree) |

## Sorties

Le pipeline produit dans le repertoire de sortie :

- `ecarts_plor_cable.geojson` : points PLOR non superposes aux cables
- `plor_doublons.geojson` : doublons de points leves
- `cheminement_superpose.geojson` : cheminements superposes
- `rapport_controles_plor.pdf` : rapport PDF de synthese

## Resultat CLI

```json
{
  "succes": true,
  "controles": {
    "controle_plor_cable": { "succes": true, "nombre_anomalies": 0 },
    "controle_plor_doublons": { "succes": true, "nombre_anomalies": 6 },
    "controle_cheminement_superpose": { "succes": true, "nombre_anomalies": 0 }
  },
  "rapport": { "succes": true, "chemin_pdf": "..." },
  "nombre_anomalies_total": 6
}
```

## Tolerance aux erreurs

- L'echec d'un controle ne bloque pas les controles suivants
- Le pipeline reste en `succes: true` meme si des controles individuels echouent
- Les anomalies sont comptabilisees uniquement pour les controles reussis

## Fonctions principales

| Fonction | Role |
| --- | --- |
| `executer_pipeline` | Execute tous les controles et le rapport |
| `main` | Point d'entree CLI |
