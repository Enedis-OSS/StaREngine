"""
Chaine de localisation d'un noeud depourvu de geometrie propre.

Un noeud sans geometrie tient sa position de son conteneur, lequel la tient
parfois d'une geometrie supplementaire. La chaine complete est donc :

    noeud -> conteneur -> geometrie supplementaire -> geometrie

Trois jeux de controles la parcourent, sur des entites et des conteneurs
differents : E-6105 / E-6106 / E-6112 (noeuds sans geometrie), E-6204 (remontees
aero-souterraines) et E-6109 (points de comptage et ouvrages collectifs). Chacun
n'en juge pas les memes maillons, mais tous la resolvent de la meme facon.

Les codes d'anomalie de la chaine sont declares ici : ils nomment la rupture,
pas le controle qui la constate, et deux controles emettent les memes.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from recostar.controle.fonctions_communes.chargement import charger_features
from recostar.controle.fonctions_communes.geojson import obtenir_id_feature
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_GEOMSUPP_HREF,
    COUCHE_GEOM_SUPP,
    COUCHES_CONTENEUR,
    EXTENSION_COUCHE,
)
from recostar.controle.fonctions_communes.proprietes import reference_href

# Cles de la geometrie GeoJSON
CLE_TYPE: str = "type"
CLE_COORDONNEES: str = "coordinates"
CLE_GEOMETRIES: str = "geometries"
TYPE_COLLECTION: str = "GeometryCollection"

# Codes d'anomalie des ruptures de la chaine, du maillon le plus proche du
# noeud au plus lointain.
TYPE_CONTENEUR_ABSENT: str = "conteneur_absent"
TYPE_CONTENEUR_INTROUVABLE: str = "conteneur_introuvable"
TYPE_GEOMSUPP_ABSENTE: str = "geometrie_supplementaire_absente"
TYPE_GEOMSUPP_INTROUVABLE: str = "geometrie_supplementaire_introuvable"
TYPE_GEOMSUPP_INVALIDE: str = "geometrie_supplementaire_invalide"


@dataclass(frozen=True, slots=True)
class Conteneur:
    """Conteneur susceptible d'heberger un noeud sans geometrie propre.

    `couche` nomme la nature du conteneur — coffret, support, batiment
    technique, enceinte cloturee. Les controles de chaine de localisation n'en
    ont pas besoin : ils partent du noeud, qui porte deja sa couche. E-3110 part
    du conteneur lui-meme, et son ecart serait sinon incapable de dire lequel.

    Le champ a une valeur par defaut : l'indexation la renseigne toujours, mais
    les constructions directes des tests n'ont pas a la fournir quand la nature
    du conteneur n'entre pas dans ce qu'elles verifient.
    """

    geometrie: dict[str, Any] | None
    href_geomsupp: str | None
    couche: str = ""


def geometrie_valide(geometrie: Any) -> bool:
    """Indique si une geometrie GeoJSON est exploitable.

    Une geometrie valide porte un type et un contenu : des coordonnees non
    vides, ou des geometries non vides pour une GeometryCollection. Une
    geometrie nulle, sans type, ou aux coordonnees vides ne localise rien — la
    reference existe alors sans rien decrire.
    """
    if not isinstance(geometrie, dict) or not geometrie.get(CLE_TYPE):
        return False
    if geometrie.get(CLE_TYPE) == TYPE_COLLECTION:
        return bool(geometrie.get(CLE_GEOMETRIES))
    return bool(geometrie.get(CLE_COORDONNEES))


def geometrie_ecart(geometrie: Any, conteneur: "Conteneur | None") -> dict[str, Any] | None:
    """Geometrie a porter par une feature d'ecart, avec repli sur le conteneur.

    L'entite en anomalie est prioritaire : c'est elle que l'operateur cherche.
    Lorsqu'elle n'a pas de position, celle de son conteneur prend le relais afin
    que l'ecart reste localisable dans un SIG ; sans conteneur resolu non plus,
    la feature est ecrite sans geometrie, ce que le format GeoJSON admet.
    """
    if geometrie is not None:
        return geometrie
    return conteneur.geometrie if conteneur is not None else None


def indexer_geometries_supplementaires(repertoire: str) -> dict[str, dict[str, Any] | None]:
    """Indexe les geometries supplementaires par identifiant."""
    features, _, _ = charger_features(repertoire, f"{COUCHE_GEOM_SUPP}{EXTENSION_COUCHE}")
    index: dict[str, dict[str, Any] | None] = {}
    for feature in features:
        identifiant = obtenir_id_feature(feature)
        if identifiant is not None:
            index[identifiant] = feature.get("geometry")
    return index


def indexer_conteneurs(repertoire: str) -> tuple[dict[str, Conteneur], list[str]]:
    """Indexe les conteneurs des quatre couches reconnues.

    Retourne (index, couches_absentes). Un noeud ne peut heriter sa position que
    d'un conteneur de ces couches : ce sont celles qui alimentent le cache de
    geometries du convertisseur.
    """
    index, _, absentes = indexer_conteneurs_autorises(repertoire, frozenset())
    return index, absentes


def indexer_conteneurs_autorises(
    repertoire: str,
    couches_autorisees: frozenset[str],
) -> tuple[dict[str, Conteneur], frozenset[str], list[str]]:
    """Indexe les conteneurs et distingue ceux des couches autorisees.

    Retourne (conteneurs, identifiants_autorises, couches_absentes). Les quatre
    couches de conteneur sont indexees : elles servent a reconnaitre une
    geometrie heritee, quelle que soit la nature du conteneur. Seuls les
    conteneurs des couches autorisees sont retenus dans le second ensemble, la
    voie du conteneur n'admettant qu'eux.

    Les deux index sont construits en une passe : relire les couches autorisees
    pour les separer serait sans benefice.

    Les couches autorisees sont un parametre et non une constante : E-6204
    n'admet que les supports, E-6109 les coffrets et batiments techniques, E-6105
    n'en distingue aucune. La mecanique d'indexation, elle, est la meme.
    """
    conteneurs: dict[str, Conteneur] = {}
    autorises: set[str] = set()
    absentes: list[str] = []
    for couche in COUCHES_CONTENEUR:
        features, _, absente = charger_features(repertoire, f"{couche}{EXTENSION_COUCHE}")
        if absente:
            absentes.append(couche)
            continue
        for feature in features:
            identifiant = obtenir_id_feature(feature)
            if identifiant is None:
                continue
            proprietes = feature.get("properties") or {}
            conteneurs[identifiant] = Conteneur(
                feature.get("geometry"),
                reference_href(proprietes, CHAMP_GEOMSUPP_HREF),
                couche,
            )
            if couche in couches_autorisees:
                autorises.add(identifiant)
    return conteneurs, frozenset(autorises), absentes


def classifier_chaine_conteneur(
    conteneur: Conteneur,
    geometries_supplementaires: Mapping[str, dict[str, Any] | None],
) -> str | None:
    """Classe la chaine conteneur -> geometrie supplementaire.

    Retourne le code d'anomalie de la premiere rupture rencontree, ou None si la
    chaine aboutit a une geometrie valide.
    """
    if conteneur.href_geomsupp is None:
        return TYPE_GEOMSUPP_ABSENTE
    if conteneur.href_geomsupp not in geometries_supplementaires:
        return TYPE_GEOMSUPP_INTROUVABLE
    if not geometrie_valide(geometries_supplementaires[conteneur.href_geomsupp]):
        return TYPE_GEOMSUPP_INVALIDE
    return None


def possede_geometrie_propre(
    geometrie: Any,
    reference: str | None,
    conteneurs: Mapping[str, Conteneur],
) -> bool:
    """Indique si une entite porte une geometrie qui lui est propre.

    Une geometrie identique a celle du conteneur a ete injectee par l'export,
    elle est donc absente a la source. Une geometrie portee sans conteneur
    resolu ne peut venir de nulle part ailleurs : elle est propre.
    """
    if not geometrie_valide(geometrie):
        return False
    conteneur = conteneurs.get(reference) if reference is not None else None
    if conteneur is None:
        return True
    return geometrie != conteneur.geometrie
