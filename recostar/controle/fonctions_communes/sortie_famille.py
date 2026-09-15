"""
Sortie GeoJSON harmonisee d'une famille de controles.

Chaque controle ecrit ses ecarts dans son propre fichier, avec les proprietes
que son domaine appelle : `fichier_source` ici, `couche` la, `id_cable` ou
`id_coffret` selon l'entite mise en cause. Utile au diagnostic d'un controle
isole, cette diversite rend la lecture d'une livraison penible : autant de
fichiers que de controles, et un schema d'attributs different dans chacun.

Ce module ramene la famille entiere a **un fichier et huit champs** :

    CODE              code du verificateur (« E-3103 »)
    CRITICITE         niveau de l'anomalie
    LIBELLE           type d'anomalie
    FAMILLE_CONTROLE  famille emettrice
    DESIGNATION_RPD   couche de l'entite en anomalie
    ID_GML            identifiant de l'entite en anomalie
    ID_GML_ASSOCIE    identifiants des autres entites en cause
    INFO              description, augmentee du detail technique

Les champs metier propres a chaque controle (seuils, mesures, indices) ne
disparaissent pas : ils sont replies dans INFO, comme la colonne homonyme du
rapport d'anomalies du verificateur. La sortie est ainsi identique d'une
famille a l'autre, quel que soit le mode d'execution — pipeline de famille,
pipeline globale ou pipeline complete, qui passent tous par ici.

Un controle lance seul en ligne de commande conserve en revanche son fichier et
ses attributs d'origine : l'harmonisation est une operation de famille.
"""

import json
import os
from collections.abc import Iterable, Mapping
from typing import Any

from recostar.controle.fonctions_communes.geojson import (
    CHAMP_CODE_CONTROLE,
    CHAMP_CODE_ERREUR,
    CHAMP_DESCRIPTION,
    CHAMP_ID_ENTITE,
    CHAMP_PRIORITE,
    CHAMP_TYPE_ANOMALIE,
    CHAMPS_COUCHE_CANDIDATS,
    EXTENSION_GEOJSON,
)

# ---------------------------------------------------------------------------
# Nomenclature de sortie
# ---------------------------------------------------------------------------

CHAMP_CODE: str = "CODE"
CHAMP_CRITICITE: str = "CRITICITE"
CHAMP_LIBELLE: str = "LIBELLE"
CHAMP_FAMILLE_CONTROLE: str = "FAMILLE_CONTROLE"
CHAMP_DESIGNATION_RPD: str = "DESIGNATION_RPD"
CHAMP_ID_GML: str = "ID_GML"
CHAMP_ID_GML_ASSOCIE: str = "ID_GML_ASSOCIE"
CHAMP_INFO: str = "INFO"

# Ordre d'apparition dans le GeoJSON produit : il fixe l'ordre des colonnes
# dans QGIS, du plus qualifiant au plus detaille.
CHAMPS_SORTIE: tuple[str, ...] = (
    CHAMP_CODE,
    CHAMP_CRITICITE,
    CHAMP_LIBELLE,
    CHAMP_FAMILLE_CONTROLE,
    CHAMP_DESIGNATION_RPD,
    CHAMP_ID_GML,
    CHAMP_ID_GML_ASSOCIE,
    CHAMP_INFO,
)

# Prefixe du fichier unique produit par famille.
PREFIXE_SORTIE_FAMILLE: str = "ecarts_"

# Separateur des valeurs multiples d'ID_GML_ASSOCIE. Meme convention que
# `cables_href` dans le modele RecoStaR : un identifiant n'en contient jamais.
SEPARATEUR_IDS: str = ","

# Champs candidats a DESIGNATION_RPD. Le socle des ecarts resout deja la couche
# sous `couche` ; la liste complete reste consultee pour les fichiers produits
# avant cette normalisation, et pour ne pas repeter ces champs dans INFO.
CHAMPS_DESIGNATION: tuple[str, ...] = CHAMPS_COUCHE_CANDIDATS

# Prefixes des champs portant un identifiant d'entite associee. `id_entite` est
# exclu : il alimente ID_GML, non ID_GML_ASSOCIE.
PREFIXES_IDENTIFIANTS: tuple[str, ...] = ("id_", "ids_")


def _nom_couche_sans_extension(valeur: Any) -> str:
    """Retire l'extension d'un champ de couche laisse sous forme de fichier."""
    texte = str(valeur)
    if texte.endswith(EXTENSION_GEOJSON):
        return texte[: -len(EXTENSION_GEOJSON)]
    return texte


def resoudre_designation(proprietes: Mapping[str, Any]) -> str:
    """Retourne la couche de l'entite en anomalie, ou une chaine vide.

    Le premier champ renseigne de CHAMPS_DESIGNATION fait foi. Une chaine vide
    plutot que None : un attribut absent et un attribut nul se lisent de la
    meme facon dans un SIG, autant n'avoir qu'un cas.
    """
    for champ in CHAMPS_DESIGNATION:
        valeur = proprietes.get(champ)
        if valeur:
            return _nom_couche_sans_extension(valeur)
    return ""


def _valeurs_identifiant(valeur: Any) -> list[str]:
    """Normalise un champ d'identifiant en liste de valeurs.

    Les controles y placent un identifiant unique, une liste, ou une chaine
    deja separee par des virgules : les trois formes sont ramenees a une liste.
    """
    if isinstance(valeur, (list, tuple, set)):
        return [str(element) for element in valeur if element]
    texte = str(valeur)
    return [part.strip() for part in texte.split(SEPARATEUR_IDS) if part.strip()]


def resoudre_ids_associes(proprietes: Mapping[str, Any], id_principal: Any) -> str:
    """Rassemble les identifiants des entites associees a l'anomalie.

    Tout champ dont le nom commence par `id_` ou `ids_` est retenu, hormis
    `id_entite` et ceux qui repetent l'identifiant principal : une entite ne
    s'associe pas a elle-meme.

    Les valeurs sont dedupliquees en conservant leur ordre de rencontre — un
    `set` rendrait la sortie instable d'une execution a l'autre.
    """
    principal = str(id_principal) if id_principal is not None else None
    associes: list[str] = []
    for champ, valeur in proprietes.items():
        if champ == CHAMP_ID_ENTITE or not champ.startswith(PREFIXES_IDENTIFIANTS):
            continue
        if not valeur:
            continue
        for identifiant in _valeurs_identifiant(valeur):
            if identifiant != principal and identifiant not in associes:
                associes.append(identifiant)
    return SEPARATEUR_IDS.join(associes)


def _champs_consommes(proprietes: Mapping[str, Any]) -> set[str]:
    """Champs deja rendus par les sept premieres colonnes de la sortie.

    Ils n'ont pas a etre repetes dans INFO, qui ne porte que ce qu'aucune
    autre colonne n'exprime.
    """
    consommes = {
        CHAMP_CODE_CONTROLE,
        CHAMP_CODE_ERREUR,
        CHAMP_PRIORITE,
        CHAMP_ID_ENTITE,
        CHAMP_TYPE_ANOMALIE,
        CHAMP_DESCRIPTION,
    }
    consommes.update(CHAMPS_DESIGNATION)
    consommes.update(champ for champ in proprietes if champ.startswith(PREFIXES_IDENTIFIANTS))
    return consommes


def construire_info(proprietes: Mapping[str, Any]) -> str:
    """Redige INFO : la description, augmentee du detail technique du controle.

    Les champs metier (seuils, mesures, comptages) sont repris sous la forme
    « nom : valeur », dans leur ordre de declaration par le controle — celui-ci
    va du plus significatif au plus accessoire. Sans eux, l'ecart serait
    qualifie mais pas mesure.
    """
    description = proprietes.get(CHAMP_DESCRIPTION)
    consommes = _champs_consommes(proprietes)
    details = [
        f"{champ} : {valeur}" for champ, valeur in proprietes.items() if champ not in consommes and valeur is not None
    ]

    texte = str(description) if description else ""
    if not details:
        return texte
    detail = ", ".join(details)
    return f"{texte} {detail}".strip()


def harmoniser_proprietes(proprietes: Mapping[str, Any], famille: str) -> dict[str, Any]:
    """Convertit les proprietes d'un ecart vers la nomenclature de sortie.

    `famille` est la cle de la famille emettrice (« cheminement », « cable »...) :
    l'identifiant stable employe partout dans le projet, de preference au
    libelle affichable, qui porte des accents et peut etre reformule.
    """
    id_entite = proprietes.get(CHAMP_ID_ENTITE)
    code = proprietes.get(CHAMP_CODE_ERREUR) or proprietes.get(CHAMP_CODE_CONTROLE)
    return {
        CHAMP_CODE: code,
        CHAMP_CRITICITE: proprietes.get(CHAMP_PRIORITE),
        CHAMP_LIBELLE: proprietes.get(CHAMP_TYPE_ANOMALIE),
        CHAMP_FAMILLE_CONTROLE: famille,
        CHAMP_DESIGNATION_RPD: resoudre_designation(proprietes),
        CHAMP_ID_GML: id_entite,
        CHAMP_ID_GML_ASSOCIE: resoudre_ids_associes(proprietes, id_entite),
        CHAMP_INFO: construire_info(proprietes),
    }


def harmoniser_feature(feature: Mapping[str, Any], famille: str) -> dict[str, Any]:
    """Convertit une feature d'ecart vers la nomenclature de sortie.

    La geometrie est reprise telle quelle : seules les proprietes changent.
    """
    return {
        "type": "Feature",
        "properties": harmoniser_proprietes(feature.get("properties") or {}, famille),
        "geometry": feature.get("geometry"),
    }


def nom_fichier_famille(famille: str) -> str:
    """Nom du fichier unique d'une famille (« ecarts_cheminement.geojson »)."""
    return f"{PREFIXE_SORTIE_FAMILLE}{famille}{EXTENSION_GEOJSON}"


def _lire_features(chemin: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Lit les features et le CRS d'un fichier d'ecarts, ou ([], None) si illisible.

    Un fichier illisible ne doit pas interrompre l'agregation : les ecarts des
    autres controles de la famille restent exploitables.
    """
    try:
        with open(chemin, encoding="utf-8") as fichier:
            collection = json.load(fichier)
    except (OSError, json.JSONDecodeError):
        return [], None
    return list(collection.get("features") or ()), collection.get("crs")


def agreger_ecarts_famille(
    chemins: Iterable[str | None],
    dossier_sortie: str,
    famille: str,
    supprimer_sources: bool = True,
) -> dict[str, Any]:
    """Fusionne les fichiers d'ecarts d'une famille en un GeoJSON unique.

    `chemins` recoit les sorties declarees par les controles, dans leur ordre
    d'execution ; les valeurs None (controle sans ecart) sont ignorees. Le
    fichier produit ne contient que les entites en anomalie de cette famille,
    aux huit champs de la nomenclature commune.

    Les fichiers sources sont supprimes une fois fusionnes : la famille ne doit
    laisser qu'un GeoJSON. `supprimer_sources` a False les conserve, ce dont un
    appelant peut avoir besoin pour comparer avant et apres.

    Retourne un compte rendu : chemin ecrit (None si aucun ecart), nombre de
    features et fichiers agreges.
    """
    features: list[dict[str, Any]] = []
    crs: dict[str, Any] | None = None
    sources: list[str] = []

    for chemin in chemins:
        if not chemin or not os.path.isfile(chemin):
            continue
        sources.append(chemin)
        lues, crs_source = _lire_features(chemin)
        if crs is None:
            crs = crs_source
        features.extend(harmoniser_feature(feature, famille) for feature in lues)

    chemin_ecrit = _ecrire_si_ecarts(features, crs, dossier_sortie, famille)

    if supprimer_sources:
        _supprimer(sources, sauf=chemin_ecrit)

    return {
        "sortie": chemin_ecrit,
        "nombre_ecarts": len(features),
        "fichiers_agreges": len(sources),
    }


def _ecrire_si_ecarts(
    features: list[dict[str, Any]],
    crs: dict[str, Any] | None,
    dossier_sortie: str,
    famille: str,
) -> str | None:
    """Ecrit le GeoJSON de famille s'il porte au moins un ecart.

    Aucun fichier n'est ecrit en l'absence d'anomalie : meme convention que
    `ecrire_geojson_si_anomalies`, un fichier vide laisserait croire a un
    controle sans resultat plutot qu'a une famille sans ecart.
    """
    chemin = os.path.join(dossier_sortie, nom_fichier_famille(famille))
    if not features:
        # Un fichier d'une execution precedente ne doit pas survivre a une
        # execution qui ne releve plus rien.
        if os.path.isfile(chemin):
            os.remove(chemin)
        return None

    collection: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        collection["crs"] = crs
    os.makedirs(dossier_sortie, exist_ok=True)
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(collection, fichier, ensure_ascii=False, indent=2)
    return chemin


def _supprimer(chemins: Iterable[str], sauf: str | None) -> None:
    """Supprime les fichiers agreges, sans toucher au fichier produit."""
    reference = os.path.abspath(sauf) if sauf else None
    for chemin in chemins:
        if reference is not None and os.path.abspath(chemin) == reference:
            continue
        try:
            os.remove(chemin)
        except OSError:
            # Un fichier deja disparu n'est pas une erreur : l'agregation a
            # atteint son but.
            continue
