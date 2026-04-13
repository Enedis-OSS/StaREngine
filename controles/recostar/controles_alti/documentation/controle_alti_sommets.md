# controle_alti_sommets.py — Contrôle altimétrique des sommets

## Description

Vérifie la cohérence altimétrique locale des sommets des câbles électriques
(`RPD_CableElectrique_Reco.geojson`). Le contrôle détecte les incohérences de Z
le long du tracé tout en évitant les faux positifs aux extrémités et sur les
tronçons aériens.

**Règles** :

- Analyse par fenêtre glissante de **4 sommets consécutifs**.
- Pour chaque fenêtre, on compare l'écart altimétrique des **2 sommets centraux**
  à la tendance définie par les **sommets extrêmes** de la fenêtre.
- Si l'**écart résiduel** (après soustraction de la tendance) est supérieur à
  **25 cm**, les 2 sommets centraux sont signalés en anomalie.
- Les **3 premiers** et **3 derniers** sommets de chaque câble sont toujours ignorés.
- Les câbles référencés par un cheminement dans `RPD_Aerien_Reco.geojson` (via
  le champ `cables_href`) sont **exclus** du contrôle.

## Fonctionnement

### 1. Chargement des données

- Lecture de `RPD_CableElectrique_Reco.geojson` (entités contrôlées).
- Lecture de `RPD_Aerien_Reco.geojson` (entités à exclure).

### 2. Construction de l'ensemble des exclusions

Pour chaque feature aérienne, le champ `cables_href` est normalisé :

- Chaîne simple → un identifiant.
- Chaîne avec séparateurs → plusieurs identifiants.
- Liste → plusieurs identifiants.

Les identifiants extraits sont stockés dans un `set` pour un test
d'appartenance en `O(1)`.

### 3. Éligibilité d'un câble

Un câble est analysé uniquement si :

- Il possède un identifiant non présent dans l'ensemble des exclusions.
- Sa géométrie est un `LineString` en **3D** (présence d'une composante Z).
- Il contient au moins 4 sommets (taille minimale de la fenêtre).

### 4. Parcours en fenêtre glissante

La fenêtre glisse sommet par sommet le long de la géométrie. Pour une fenêtre
indicée `[i, i+1, i+2, i+3]`, les sommets centraux analysés sont `i+1` et
`i+2`. La plage des fenêtres analysées est calculée de sorte que les **3
premiers** et **3 derniers** sommets du câble ne soient jamais centraux.

Conséquence : chaque sommet central apparaît dans **plusieurs fenêtres**. L'écart
résiduel maximal observé est conservé afin de refléter la situation la plus sévère.

### 5. Calcul de l'écart résiduel

Soit une fenêtre `(P0, P1, P2, P3)` avec composantes `(x, y, z)` :

1. Distance planaire totale : `d03 = hypot(P3.x - P0.x, P3.y - P0.y)`.
2. Écart brut observé : `dZ_brut = P2.z - P1.z`.
3. Si `d03 <= 0` (fenêtre dégénérée en 2D) → on retient `|dZ_brut|`.
4. Sinon, pente contextuelle : `pente = (P3.z - P0.z) / d03`.
5. Écart attendu entre centraux : `dZ_attendu = pente * hypot(P2-P1)`.
6. **Écart résiduel** : `|dZ_brut - dZ_attendu|`.

Cette soustraction neutralise la pente naturelle du tracé : une pente régulière
ne génère donc **aucune anomalie**. Seules les ruptures altimétriques locales
(pics, creux, décrochages) sont détectées.

### 6. Décision d'anomalie

Si l'écart résiduel est strictement supérieur à `SEUIL_ECART_ALTI` (0,25 m),
les deux sommets centraux de la fenêtre sont marqués en anomalie.

## Paramètres

| Constante            | Valeur | Description                                        |
| -------------------- | ------ | -------------------------------------------------- |
| `SEUIL_ECART_ALTI`   | `0.25` | Seuil d'écart résiduel en mètres                   |
| `NB_SOMMETS_IGNORES` | `3`    | Sommets ignorés en début et fin de chaque câble    |
| `TAILLE_FENETRE`     | `4`    | Taille de la fenêtre glissante                     |

## Ligne de commande

```bash
python controle_alti_sommets.py --repertoire <chemin> [--sortie <chemin>]
```

| Argument       | Obligatoire | Description                                                          |
| -------------- | ----------- | -------------------------------------------------------------------- |
| `--repertoire` | Oui         | Répertoire contenant `RPD_CableElectrique_Reco` et `RPD_Aerien_Reco` |
| `--sortie`     | Non         | Répertoire de sortie (défaut : même que `--repertoire`)              |

### Sortie

- `ecarts_controle_alti_sommets.geojson` — FeatureCollection de points
  représentant les sommets en anomalie, avec les propriétés suivantes :

| Propriété          | Description                                           |
| ------------------ | ----------------------------------------------------- |
| `id_cable`         | Identifiant du câble parent                           |
| `indice_sommet`    | Indice du sommet dans la géométrie du câble           |
| `ecart_residuel_m` | Écart résiduel maximal observé en mètres              |
| `seuil_m`          | Seuil de déclenchement (valeur de `SEUIL_ECART_ALTI`) |
| `type_anomalie`    | `ecart_altimetrique_sommet`                           |
| `priorite`         | Niveau de priorité de l'anomalie (`bloquant`)         |

Le rapport console JSON retourne :

```json
{
  "succes": true,
  "nombre_anomalies": 26,
  "cables_exclus": 4,
  "sortie": "…/ecarts_controle_alti_sommets.geojson"
}
```

## Exemple visuel

A réaliser

## Utilisation en tant que bibliothèque

```python
from controle_alti_sommets import (
    collecter_ids_cables_aeriens,
    controler_altimetrie_sommets,
    construire_geojson_ecarts,
    executer_controle_cli,
)

# Exclusion des câbles référencés par l'aérien
ids_exclus = collecter_ids_cables_aeriens(features_aerien)

# Logique métier seule
anomalies = controler_altimetrie_sommets(cables, ids_exclus)

# Sérialisation GeoJSON
geojson = construire_geojson_ecarts(anomalies)

# Contrôle complet avec écriture des fichiers
resultat = executer_controle_cli(repertoire, sortie)
```

## Tests

Les tests unitaires se trouvent dans `test_controle_alti_sommets.py` (même
répertoire que le script). Ils couvrent :

- Calcul de l'écart résiduel (ligne plate, pente régulière, pic, fenêtre dégénérée).
- Plage de fenêtres analysables selon le nombre de sommets.
- Détection et non-détection des anomalies selon leur position.
- Normalisation du champ `cables_href` (chaîne, liste, chaîne multi-valeurs).
- Exclusion effective des câbles aériens.
- Rejet des câbles 2D ou trop courts.
- Structure du GeoJSON de sortie.
- Exécution CLI bout en bout via `tmp_path`.

```bash
pytest test_controle_alti_sommets.py -v
```
