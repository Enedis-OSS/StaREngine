"""
Utilitaires communs pour la manipulation de fichiers GeoJSON.

Module partage par les domaines altimetrie, projection et cheminement.
Centralise les fonctions de lecture, ecriture, listage et extraction
d'identifiant utilisees dans l'ensemble des controles, ainsi que la
normalisation du socle commun des proprietes des features d'ecarts.
"""

import json
import os
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Extension des fichiers traites
EXTENSION_GEOJSON: str = ".geojson"

# Prefixe des fichiers d'ecarts (exclus de l'analyse)
PREFIXE_ECARTS: str = "ecarts_"

# Socle commun present dans les proprietes de toute feature d'ecart, quel que
# soit le controle. Les champs metier specifiques sont conserves a la suite.
CHAMP_CODE_CONTROLE: str = "code_controle"
CHAMP_PRIORITE: str = "priorite"
CHAMP_ID_ENTITE: str = "id_entite"
CHAMP_TYPE_ANOMALIE: str = "type_anomalie"
CHAMP_DESCRIPTION: str = "description"

# Ordre d'apparition du socle en tete des proprietes (lisibilite dans QGIS).
CHAMPS_SOCLE: tuple[str, ...] = (
    CHAMP_CODE_CONTROLE,
    CHAMP_PRIORITE,
    CHAMP_ID_ENTITE,
    CHAMP_TYPE_ANOMALIE,
    CHAMP_DESCRIPTION,
)


@dataclass(frozen=True, slots=True)
class ProfilEcarts:
    """Identite d'un controle, utilisee pour normaliser ses features d'ecarts.

    - `code_controle` : code affichable du controle (« E200 »).
    - `descriptions` : phrase decrivant chaque `type_anomalie` produit.
    - `champs_id` : champs candidats pour `id_entite`, par ordre de priorite ;
      le premier renseigne designe l'entite en anomalie. Plusieurs champs sont
      necessaires aux controles dont l'identifiant depend du type d'anomalie
      (E401) ou qui mettent en relation deux entites (E400, E500, E507).
    """

    code_controle: str
    descriptions: Mapping[str, str]
    champs_id: tuple[str, ...] = (CHAMP_ID_ENTITE,)


def lire_geojson(chemin: str) -> dict[str, Any] | None:
    """Charge un fichier GeoJSON et retourne son contenu, ou None si absent."""
    chemin = str(Path(chemin).resolve())
    if not os.path.isfile(chemin):
        return None
    with open(chemin, encoding="utf-8") as fichier:
        return json.load(fichier)


def ecrire_geojson(donnees: dict[str, Any], chemin: str) -> None:
    """Ecrit un FeatureCollection GeoJSON sur disque."""
    chemin = str(Path(chemin).resolve())
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(donnees, fichier, ensure_ascii=False, indent=2)


def ecrire_geojson_si_anomalies(donnees: dict[str, Any], chemin: str) -> str | None:
    """Ecrit le GeoJSON d'ecarts uniquement si au moins une anomalie est presente.

    Retourne le chemin ecrit, ou None lorsqu'aucune anomalie n'est detectee.
    Un fichier issu d'une execution precedente est alors supprime afin que la
    presence du fichier reste un indicateur fiable d'ecarts.
    """
    chemin_resolu = str(Path(chemin).resolve())
    if donnees.get("features"):
        ecrire_geojson(donnees, chemin_resolu)
        return chemin_resolu
    if os.path.isfile(chemin_resolu):
        os.remove(chemin_resolu)
    return None


def lister_fichiers_geojson(repertoire: str) -> list[str]:
    """Liste les fichiers GeoJSON eligibles dans le repertoire.

    Exclut les fichiers d'ecarts (prefixe 'ecarts_') pour eviter
    l'analyse des sorties de controles precedents.
    """
    repertoire = str(Path(repertoire).resolve())
    fichiers: list[str] = []
    for nom in sorted(os.listdir(repertoire)):
        if not nom.lower().endswith(EXTENSION_GEOJSON):
            continue
        if nom.lower().startswith(PREFIXE_ECARTS):
            continue
        fichiers.append(nom)
    return fichiers


def compter_anomalies_par_type(anomalies: list[dict[str, Any]]) -> dict[str, int]:
    """Ventile les anomalies par type d'anomalie, pour le rapport JSON.

    Tous les controles a sortie GeoJSON produisent cette ventilation a partir
    de la meme cle `type_anomalie` : elle est mutualisee ici plutot que
    redefinie a l'identique dans chacun d'eux.

    `Counter` denombre en une passe au niveau C, la ou une boucle Python
    explicite paie un appel d'interpreteur par anomalie.
    """
    return dict(Counter(anomalie[CHAMP_TYPE_ANOMALIE] for anomalie in anomalies))


def obtenir_id_feature(feature: dict[str, Any]) -> str | None:
    """Retourne l'identifiant metier d'une feature GeoJSON."""
    proprietes = feature.get("properties") or {}
    valeur = proprietes.get("id")
    if isinstance(valeur, (str, int)):
        return str(valeur)
    return None


def _resoudre_id_entite(proprietes: Mapping[str, Any], champs_id: tuple[str, ...]) -> str | None:
    """Retourne le premier identifiant renseigne parmi les champs candidats."""
    for champ in champs_id:
        valeur = proprietes.get(champ)
        if valeur is not None and valeur != "":
            return str(valeur)
    return None


def _proprietes_normalisees(proprietes: Mapping[str, Any], profil: ProfilEcarts) -> dict[str, Any]:
    """Prefixe les proprietes d'une feature par le socle commun.

    Les champs metier existants sont conserves tels quels ; ceux qui portent
    deja un nom du socle (`type_anomalie`, `priorite`, `id_entite`) ne sont pas
    dupliques, ils sont simplement remontes en tete.
    """
    type_anomalie = proprietes.get(CHAMP_TYPE_ANOMALIE)
    normalisees: dict[str, Any] = {
        CHAMP_CODE_CONTROLE: profil.code_controle,
        CHAMP_PRIORITE: proprietes.get(CHAMP_PRIORITE),
        CHAMP_ID_ENTITE: _resoudre_id_entite(proprietes, profil.champs_id),
        CHAMP_TYPE_ANOMALIE: type_anomalie,
        # Repli sur le code technique si un type n'est pas encore decrit :
        # une description manquante ne doit pas faire echouer un controle.
        CHAMP_DESCRIPTION: profil.descriptions.get(str(type_anomalie), str(type_anomalie)),
    }
    for champ, valeur in proprietes.items():
        if champ not in CHAMPS_SOCLE:
            normalisees[champ] = valeur
    return normalisees


def normaliser_geojson_ecarts(geojson: dict[str, Any], profil: ProfilEcarts) -> dict[str, Any]:
    """Applique le socle commun aux proprietes de chaque feature d'ecart.

    La collection est modifiee in situ (aucune copie des features) puis
    retournee, afin de s'inserer directement dans les `return` existants.
    """
    for feature in geojson.get("features", ()):
        feature["properties"] = _proprietes_normalisees(feature.get("properties") or {}, profil)
    return geojson
