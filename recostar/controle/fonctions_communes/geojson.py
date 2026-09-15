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

from recostar.controle.codes_verificateur import (
    NIVEAU_BASSE,
    NIVEAU_FORTE,
    NIVEAU_MOYENNE,
    niveau_anomalie,
    resoudre_code_erreur,
)

# Vocabulaire de priorite mis a disposition des modules de controle. Un controle
# ne declare plus sa priorite que pour les types d'anomalie dont le code
# d'erreur n'est pas encore fixe ; il l'exprime alors avec les niveaux du
# referentiel, importes et jamais recopies, ce qui interdit toute derive entre
# l'echelle des controles et celle du verificateur. `bloquante` n'est pas
# reexportee : elle n'est jamais emise (cf. `niveau_anomalie`).
PRIORITE_FORTE: str = NIVEAU_FORTE
PRIORITE_MOYENNE: str = NIVEAU_MOYENNE
PRIORITE_BASSE: str = NIVEAU_BASSE

# Extension des fichiers traites
EXTENSION_GEOJSON: str = ".geojson"

# Prefixe des fichiers d'ecarts (exclus de l'analyse)
PREFIXE_ECARTS: str = "ecarts_"

# Socle commun present dans les proprietes de toute feature d'ecart, quel que
# soit le controle. Les champs metier specifiques sont conserves a la suite.
CHAMP_CODE_CONTROLE: str = "code_controle"
# Code du verificateur RecoStaR qualifiant la cause exacte de l'anomalie. Il
# s'ajoute a `code_controle`, jamais ne s'y substitue : les consommateurs qui
# filtrent sur le controle emetteur (QGIS) restent valides.
CHAMP_CODE_ERREUR: str = "code_erreur"
CHAMP_PRIORITE: str = "priorite"
CHAMP_ID_ENTITE: str = "id_entite"
CHAMP_TYPE_ANOMALIE: str = "type_anomalie"
CHAMP_DESCRIPTION: str = "description"
# Couche de l'entite en anomalie. Les controles la nomment de plusieurs facons
# selon leur domaine ; CHAMPS_COUCHE_CANDIDATS les recense, et le socle ramene
# la premiere renseignee sous ce nom-la.
CHAMP_COUCHE: str = "couche"

# Ordre d'apparition du socle en tete des proprietes (lisibilite dans QGIS).
CHAMPS_SOCLE: tuple[str, ...] = (
    CHAMP_CODE_CONTROLE,
    CHAMP_CODE_ERREUR,
    CHAMP_PRIORITE,
    CHAMP_ID_ENTITE,
    CHAMP_TYPE_ANOMALIE,
    CHAMP_DESCRIPTION,
    CHAMP_COUCHE,
)

# Champs sous lesquels un controle peut designer la couche d'une entite, par
# ordre de preference : les premiers designent l'entite en anomalie, les
# suivants une entite associee. Un controle mono-couche n'en porte aucun et
# declare sa couche dans son ProfilEcarts.
CHAMPS_COUCHE_CANDIDATS: tuple[str, ...] = (
    CHAMP_COUCHE,
    "fichier_source",
    "couche_noeud",
    "couche_a",
    "fichier_cheminement",
    "fichier_cable",
    "couche_reference",
)


@dataclass(frozen=True, slots=True)
class ProfilEcarts:
    """Identite d'un controle, utilisee pour normaliser ses features d'ecarts.

    - `code_controle` : code affichable du controle (« E-5107 »).
    - `descriptions` : phrase decrivant chaque `type_anomalie` produit.
    - `champs_id` : champs candidats pour `id_entite`, par ordre de priorite ;
      le premier renseigne designe l'entite en anomalie. Plusieurs champs sont
      necessaires aux controles dont l'identifiant depend du type d'anomalie
      (E-9400) ou qui mettent en relation deux entites (E-5108, E-9500, E-9502).
    """

    code_controle: str
    descriptions: Mapping[str, str]
    champs_id: tuple[str, ...] = (CHAMP_ID_ENTITE,)
    # Couche de l'entite que le controle met en cause, pour les controles dont
    # les anomalies ne la nomment pas — la source y est implicite, une seule
    # couche etant analysee. Sans elle, la sortie de famille laisserait le
    # champ DESIGNATION_RPD vide.
    couche_source: str | None = None


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


def compter_ecarts_par_type(geojson_ecarts: dict[str, Any]) -> dict[str, int]:
    """Ventile par type d'anomalie les features d'un GeoJSON d'ecarts normalise.

    Pendant de `compter_anomalies_par_type`, qui opere sur la liste d'anomalies
    brutes : tous les controles n'y portent pas de `type_anomalie`, alors que le
    socle commun le garantit sur chaque feature. C'est la ventilation dont la
    synthese a besoin pour deriver la priorite de chaque type depuis son code
    d'erreur ; sans elle, un controle qui ne declare plus de priorite scalaire
    verrait ses anomalies rangees en « non precisee ».
    """
    types = (
        (feature.get("properties") or {}).get(CHAMP_TYPE_ANOMALIE) for feature in geojson_ecarts.get("features", ())
    )
    return dict(Counter(type_anomalie for type_anomalie in types if type_anomalie is not None))


def obtenir_id_feature(feature: dict[str, Any]) -> str | None:
    """Retourne l'identifiant metier d'une feature GeoJSON."""
    proprietes = feature.get("properties") or {}
    valeur = proprietes.get("id")
    if isinstance(valeur, (str, int)):
        return str(valeur)
    return None


def _nom_couche(valeur: Any) -> str:
    """Ramene un champ de couche a son nom de couche, sans extension de fichier.

    Les controles y inscrivent tantot la couche (« RPD_Coffret_Reco »), tantot
    son fichier (« RPD_Coffret_Reco.geojson ») : le socle n'en expose qu'une
    forme.
    """
    texte = str(valeur)
    if texte.endswith(EXTENSION_GEOJSON):
        return texte[: -len(EXTENSION_GEOJSON)]
    return texte


def _resoudre_couche(proprietes: Mapping[str, Any], couche_source: str | None) -> str | None:
    """Retourne la couche de l'entite en anomalie.

    Le premier champ renseigne de CHAMPS_COUCHE_CANDIDATS fait foi ; a defaut,
    la couche declaree par le profil du controle, qui n'en analyse qu'une.
    """
    for champ in CHAMPS_COUCHE_CANDIDATS:
        valeur = proprietes.get(champ)
        if valeur:
            return _nom_couche(valeur)
    return _nom_couche(couche_source) if couche_source else None


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

    `code_erreur` est resolu ici, seul point d'insertion commun aux 32 controles
    a sortie GeoJSON : aucun module de controle n'a a le declarer. `priorite`
    en est deduite au meme endroit — elle est une propriete du code d'erreur, et
    la valeur eventuellement portee par le controle ne sert que de repli pour
    les types d'anomalie dont le code n'est pas encore fixe.
    """
    type_anomalie = proprietes.get(CHAMP_TYPE_ANOMALIE)
    cle_anomalie = str(type_anomalie) if type_anomalie is not None else None
    normalisees: dict[str, Any] = {
        CHAMP_CODE_CONTROLE: profil.code_controle,
        CHAMP_CODE_ERREUR: resoudre_code_erreur(profil.code_controle, cle_anomalie),
        CHAMP_PRIORITE: niveau_anomalie(profil.code_controle, cle_anomalie, proprietes.get(CHAMP_PRIORITE)),
        CHAMP_ID_ENTITE: _resoudre_id_entite(proprietes, profil.champs_id),
        CHAMP_TYPE_ANOMALIE: type_anomalie,
        # Repli sur le code technique si un type n'est pas encore decrit :
        # une description manquante ne doit pas faire echouer un controle.
        CHAMP_DESCRIPTION: profil.descriptions.get(str(type_anomalie), str(type_anomalie)),
        CHAMP_COUCHE: _resoudre_couche(proprietes, profil.couche_source),
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
