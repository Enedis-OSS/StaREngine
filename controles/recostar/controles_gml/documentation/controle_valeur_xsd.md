# controle_valeur_xsd.py — Contrôle de conformité des valeurs XSD

## Description

Vérifie que les valeurs des champs soumis à des listes autorisées (Énumérations
et CodeLists du modèle RecoStaR) sont conformes aux référentiels définis dans
`referentiels/recostar/recostar_referentiels_V1_1.json`.

**Règle** :

- Pour chaque fichier `RPD_*.geojson`, les champs dont le domaine de valeurs est
  contraint par le modèle XSD doivent contenir uniquement des valeurs autorisées.
- Les valeurs vides (`null` ou chaîne vide) sont ignorées : la présence
  obligatoire des champs relève d'un autre contrôle.
- Ce contrôle est **bloquant** : toute valeur non conforme doit être corrigée
  avant l'export.

## Fonctionnement

### 1. Listage des fichiers

Le script parcourt le répertoire d'entrée et sélectionne tous les fichiers dont
le nom commence par `RPD_` et se termine par `.geojson`, triés par ordre
alphabétique.

### 2. Chargement du référentiel

Le fichier `recostar_referentiels_V1_1.json` est chargé et indexé. Chaque type
de référence est associé à un ensemble (`set`) de valeurs autorisées pour des
vérifications en O(1).

### 3. Contrôle des valeurs

Pour chaque fichier GeoJSON, un mapping statique (`MAPPING_CHAMPS_TYPES`)
détermine quels champs sont soumis à un contrôle et quel type de référence
s'applique. Chaque feature est parcourue et les valeurs non conformes sont
signalées.

### 4. Génération des sorties

- **Rapport JSON** (`rapport_controle_valeur_xsd.json`) : synthèse globale du
  contrôle avec le nombre de fichiers analysés, le nombre de features, le nombre
  d'anomalies et le détail des écarts.
- **GeoJSON des écarts par fichier** (`ecarts_valeur_xsd_<nom>.geojson`) : un
  fichier par GeoJSON d'entrée présentant des écarts, avec le CRS propagé pour
  l'affichage dans QGIS.
- **GeoJSON des écarts agrégé** (`ecarts_valeur_xsd.geojson`) : FeatureCollection
  regroupant l'ensemble des écarts de tous les fichiers, utilisé pour le rapport
  PDF de synthèse.

## Ligne de commande

```bash
python controle_valeur_xsd.py --repertoire <chemin> [--sortie <chemin>] [--referentiel <chemin>]
```

| Argument        | Obligatoire | Description                                                          |
| --------------- | ----------- | -------------------------------------------------------------------- |
| `--repertoire`  | Oui         | Répertoire contenant les fichiers `RPD_*.geojson`                    |
| `--sortie`      | Non         | Répertoire de sortie (défaut : même que `--repertoire`)              |
| `--referentiel` | Non         | Chemin du JSON des référentiels (défaut : résolution automatique)    |

### Sortie

- `rapport_controle_valeur_xsd.json` — rapport synthétique au format JSON :

```json
{
  "controle": "valeur_xsd",
  "bloquant": true,
  "nombre_fichiers_analyses": 17,
  "nombre_features_total": 607,
  "nombre_anomalies": 2,
  "fichiers": [
    {
      "fichier": "RPD_Jonction_Reco.geojson",
      "nombre_features": 50,
      "nombre_ecarts": 2
    }
  ],
  "anomalies": [
    {
      "fichier": "RPD_Jonction_Reco.geojson",
      "id_entite": "jonction_001",
      "ecarts": [
        {
          "champ": "DomaineTension",
          "type_reference": "DomaineTensionValue",
          "valeur": "HTZ"
        }
      ]
    }
  ]
}
```

- `ecarts_valeur_xsd_<nom>.geojson` — FeatureCollection des anomalies par fichier
  source (un fichier par GeoJSON d'entrée présentant des écarts).

- `ecarts_valeur_xsd.geojson` — FeatureCollection agrégée de l'ensemble des
  anomalies :

| Propriété        | Description                                      |
| ---------------- | ------------------------------------------------ |
| `id_entite`      | Identifiant de l'entité en écart                 |
| `fichier_source` | Nom du fichier contenant cette entité            |
| `type_anomalie`  | `valeur_non_conforme_xsd`                        |
| `message`        | Description détaillée des écarts                 |
| `priorite`       | Niveau de priorité (`bloquant`)                  |

## Fichiers contrôlés et champs vérifiés

| Fichier GeoJSON                        | Champs contrôlés                                                                                   |
| -------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `RPD_CableElectrique_Reco`             | DomaineTension, Isolant, Materiau, HierarchieBT, Statut, FonctionCable_href                        |
| `RPD_CableTerre_Reco`                  | Materiau, Statut, PrecisionXY, PrecisionZ                                                          |
| `RPD_CableTelecommunication_Reco`      | Fonction, Statut                                                                                   |
| `RPD_Jonction_Reco`                    | DomaineTension, TypeJonction, Statut, PrecisionXY, PrecisionZ                                      |
| `RPD_Coffret_Reco`                     | TypeCoffret_href, FonctionCoffret_href, ImplantationArmoire_href, Statut, PrecisionXY, PrecisionZ  |
| `RPD_Support_Reco`                     | NatureSupport_href, Matiere_href, Classe_href, Statut, PrecisionXY, PrecisionZ                     |
| `RPD_PosteElectrique_Reco`             | Categorie_href, TypePoste_href, Statut                                                             |
| `RPD_Terre_Reco`                       | NatureTerre_href, Statut                                                                           |
| `RPD_Fourreau_Reco`                    | Materiau, EtatCoupeType, Statut, PrecisionXY, PrecisionZ                                           |
| `RPD_PleineTerre_Reco`                 | EtatCoupeType, PrecisionXY, PrecisionZ                                                             |
| `RPD_ProtectionMecanique_Reco`         | Materiau, EtatCoupeType, PrecisionXY, PrecisionZ                                                   |
| `RPD_Aerien_Reco`                      | ModePose, Statut, PrecisionXY, PrecisionZ                                                          |
| `RPD_PointDeComptage_Reco`             | Statut, PrecisionXY, PrecisionZ                                                                    |
| `RPD_BatimentTechnique_Reco`           | Statut                                                                                             |
| `RPD_EnceinteCloturee_Reco`            | Statut                                                                                             |
| `RPD_CoupeCircuitAFusibles_Reco`       | Statut                                                                                             |
| `RPD_JeuBarres_Reco`                   | Statut                                                                                             |
| `RPD_SupportModules_Reco`              | Statut                                                                                             |
| `RPD_OuvrageCollectifBranchement_Reco` | Statut                                                                                             |

## Utilisation en tant que bibliothèque

```python
from controle_valeur_xsd import (
    lister_fichiers_rpd,
    charger_referentiel,
    controler_fichier,
    construire_rapport_json,
    construire_geojson_ecarts,
    executer_controle_cli,
)

# Controle complet avec ecriture des fichiers
resultat = executer_controle_cli(repertoire, sortie)
```

## Tests

Les tests unitaires se trouvent dans `test_controle_valeur_xsd.py` (même
répertoire que le script). Ils couvrent :

- Construction de l'index des valeurs autorisées.
- Détection d'écarts sur des valeurs non conformes.
- Ignorance des valeurs vides (`null` ou chaîne vide).
- Gestion des types de référence absents du référentiel.
- Contrôle de fichiers complets avec mélange de valeurs conformes et non
  conformes.
- Propagation du CRS dans le GeoJSON de sortie.
- Structure du rapport JSON agrégé.
- Génération du fichier d'écarts agrégé (`ecarts_valeur_xsd.geojson`).
- Exécution CLI bout en bout via `tmp_path`.

```bash
pytest test_controle_valeur_xsd.py -v
```
