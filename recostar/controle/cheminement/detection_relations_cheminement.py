"""
Moteur de detection : integrite des relations entre cables et cheminements.

Verifie la coherence bidirectionnelle entre les entites cable et les entites
cheminement via le champ cables_href. Quatre regles sont appliquees :

  Regle 1 / Regle 3 — Cable non reference :
      Toute entite cable absente de tout cables_href est signalee.

  Regle 2 — Reference orpheline :
      Toute valeur de cables_href ne correspondant pas a l'identifiant
      d'une entite cable existante est signalee.

  Regle 4 — Cardinalite :
      Un cheminement doit etre associe a exactement un cable.
      Un cheminement sans cables_href (null ou absent) et un cheminement
      referençant plusieurs cables sont tous deux signales.

Fichiers cables analyses :
  RPD_CableElectrique_Reco.geojson
  RPD_CableTerre_Reco.geojson
  RPD_CableTelecommunication_Reco.geojson

Fichiers cheminement analyses — les cinq voies du modele :
  RPD_Fourreau_Reco.geojson
  RPD_Galerie_Reco.geojson
  RPD_PleineTerre_Reco.geojson
  RPD_ProtectionMecanique_Reco.geojson
  RPD_Aerien_Reco.geojson

"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.ecarts import filtrer_par_type
from recostar.controle.fonctions_communes.geojson import (
    ProfilEcarts,
    compter_anomalies_par_type,
    ecrire_geojson_si_anomalies,
    lire_geojson,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_CABLES_HREF,
    CHAMP_ETAT_COUPE_TYPE,
    ETAT_COUPE_PROVISOIRE,
    FICHIER_CABLE_ELECTRIQUE,
    FICHIER_CABLE_TELECOM,
    FICHIER_CABLE_TERRE,
    FICHIER_FOURREAU,
    FICHIERS_CHEMINEMENT,
)
from recostar.controle.fonctions_communes.references_cables import extraire_ids_cables_href as _extraire_ids_cables_href

# Fichiers cable dont les entites doivent etre referenceees par les cheminements
FICHIERS_CABLES: tuple[str, ...] = (
    FICHIER_CABLE_ELECTRIQUE,
    FICHIER_CABLE_TERRE,
    FICHIER_CABLE_TELECOM,
)

# Fichiers cheminement porteurs du champ cables_href : les cinq du modele. La
# liste etait dupliquee ici et dans E-5108, qui parcourt les memes couches.


@dataclass(slots=True)
class EntiteCable:
    """Entite cable avec son identifiant, son fichier source et sa geometrie."""

    id_entite: str
    fichier: str
    geometrie: dict[str, Any] | None


@dataclass(slots=True)
class EntiteCheminement:
    """Entite cheminement avec ses references cables et sa geometrie."""

    id_entite: str | None
    fichier: str
    ids_cables: list[str]  # identifiants extraits du champ cables_href
    geometrie: dict[str, Any] | None
    # Etat de la coupe-type, champ optionnel : None quand il n'est pas renseigne,
    # et sur l'aerien, que le XSD n'en dote pas.
    etat_coupe_type: str | None = None


# ---------------------------------------------------------------------------
# Chargement des entites
# ---------------------------------------------------------------------------


def charger_cables(
    repertoire: str,
) -> tuple[dict[str, EntiteCable], list[str]]:
    """Charge toutes les entites cable depuis les fichiers concernes.

    Retourne ({id_cable: EntiteCable}, fichiers_absents).
    Les entites sans identifiant sont ignorees silencieusement.
    """
    cables: dict[str, EntiteCable] = {}
    fichiers_absents: list[str] = []

    for nom_fichier in FICHIERS_CABLES:
        chemin = os.path.join(repertoire, nom_fichier)
        if not os.path.isfile(chemin):
            fichiers_absents.append(nom_fichier)
            continue
        collection = lire_geojson(chemin)
        if collection is None:
            continue
        for feature in collection.get("features", []):
            id_entite = obtenir_id_feature(feature)
            if id_entite is None:
                continue
            cables[id_entite] = EntiteCable(
                id_entite=id_entite,
                fichier=nom_fichier,
                geometrie=feature.get("geometry"),
            )

    return cables, fichiers_absents


def _creer_entite_cheminement(
    feature: dict[str, Any],
    nom_fichier: str,
) -> EntiteCheminement:
    """Cree une EntiteCheminement depuis une feature GeoJSON."""
    props = feature.get("properties") or {}
    return EntiteCheminement(
        id_entite=obtenir_id_feature(feature),
        fichier=nom_fichier,
        ids_cables=_extraire_ids_cables_href(props.get(CHAMP_CABLES_HREF)),
        geometrie=feature.get("geometry"),
        etat_coupe_type=props.get(CHAMP_ETAT_COUPE_TYPE),
    )


def charger_cheminements(
    repertoire: str,
) -> tuple[list[EntiteCheminement], list[str], dict[str, Any] | None]:
    """Charge toutes les entites cheminement depuis les fichiers concernes.

    Retourne (cheminements, fichiers_absents, crs).
    """
    cheminements: list[EntiteCheminement] = []
    fichiers_absents: list[str] = []
    crs: dict[str, Any] | None = None

    for nom_fichier in FICHIERS_CHEMINEMENT:
        chemin = os.path.join(repertoire, nom_fichier)
        if not os.path.isfile(chemin):
            fichiers_absents.append(nom_fichier)
            continue
        collection = lire_geojson(chemin)
        if collection is None:
            continue
        if crs is None:
            crs = collection.get("crs")
        for feature in collection.get("features", []):
            cheminements.append(_creer_entite_cheminement(feature, nom_fichier))

    return cheminements, fichiers_absents, crs


# ---------------------------------------------------------------------------
# Construction des anomalies unitaires
# ---------------------------------------------------------------------------


def _anomalie_cable_non_reference(cable: EntiteCable) -> dict[str, Any]:
    """Construit l'anomalie pour un cable sans reference cheminement (regles 1 et 3)."""
    return {
        "type_anomalie": "cable_non_reference",
        "fichier_cable": cable.fichier,
        "id_cable": cable.id_entite,
        "geometrie": cable.geometrie,
    }


def _anomalie_sans_cable(cheminement: EntiteCheminement) -> dict[str, Any]:
    """Construit l'anomalie pour un cheminement sans cables_href (regle 4)."""
    return {
        "type_anomalie": "cheminement_sans_cable",
        "fichier_cheminement": cheminement.fichier,
        "id_cheminement": cheminement.id_entite,
        "geometrie": cheminement.geometrie,
    }


def _anomalie_fourreau_sans_cable(cheminement: EntiteCheminement) -> dict[str, Any]:
    """Construit l'anomalie pour un fourreau sans cables_href (regle 4).

    Type distinct de `cheminement_sans_cable` : c'est a cette maille que le
    niveau de l'ecart se declare, et le fourreau sans cable deroge au niveau de
    son code (cf. codes_verificateur.DEROGATIONS_NIVEAU).
    """
    return {
        "type_anomalie": "fourreau_sans_cable",
        "fichier_cheminement": cheminement.fichier,
        "id_cheminement": cheminement.id_entite,
        "etat_coupe_type": cheminement.etat_coupe_type,
        "geometrie": cheminement.geometrie,
    }


def _anomalie_multi_cables(cheminement: EntiteCheminement) -> dict[str, Any]:
    """Construit l'anomalie pour un cheminement referençant plusieurs cables (regle 4)."""
    return {
        "type_anomalie": "cheminement_multi_cables",
        "fichier_cheminement": cheminement.fichier,
        "id_cheminement": cheminement.id_entite,
        "nb_cables": len(cheminement.ids_cables),
        "cables_href": ",".join(cheminement.ids_cables),
        "geometrie": cheminement.geometrie,
    }


def _anomalie_reference_orpheline(
    cheminement: EntiteCheminement,
    id_cable_invalide: str,
) -> dict[str, Any]:
    """Construit l'anomalie pour une reference cables_href sans cable correspondant (regle 2)."""
    return {
        "type_anomalie": "reference_orpheline",
        "fichier_cheminement": cheminement.fichier,
        "id_cheminement": cheminement.id_entite,
        "cables_href_invalide": id_cable_invalide,
        "geometrie": cheminement.geometrie,
    }


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def _anomalie_absence_de_cable(cheminement: EntiteCheminement) -> dict[str, Any] | None:
    """Qualifie l'absence de cable sur un cheminement, ou l'admet.

    Le fourreau est traite a part des trois autres couches de cheminement. Un
    fourreau pose sans cable associe n'est pas un defaut de recolement : il peut
    etre pose en attente de cablage. Deux consequences, et elles seules :

    - **coupe-type provisoire** : le contenu du fourreau n'est pas encore arrete,
      l'absence de cable est donc nominale et aucun ecart n'est emis ;
    - **coupe-type definitive ou absente** : l'ecart est emis sous un type qui
      lui est propre, `fourreau_sans_cable`, seule maille a laquelle son niveau
      basse se declare (cf. codes_verificateur.DEROGATIONS_NIVEAU).

    Les autres cheminements sans cable conservent `cheminement_sans_cable` et le
    niveau de leur code, quel que soit leur etat de coupe-type.
    """
    if cheminement.fichier != FICHIER_FOURREAU:
        return _anomalie_sans_cable(cheminement)
    if cheminement.etat_coupe_type == ETAT_COUPE_PROVISOIRE:
        return None
    return _anomalie_fourreau_sans_cable(cheminement)


def _analyser_cheminement(
    cheminement: EntiteCheminement,
    ids_cables_valides: set[str],
) -> list[dict[str, Any]]:
    """Detecte les anomalies d'un cheminement (regles 2 et 4).

    Les regles de cardinalite (0 ou >1 cable) et de validite des references
    sont appliquees independamment : un cheminement peut cumuler plusieurs
    types d'anomalies.
    """
    anomalies: list[dict[str, Any]] = []
    ids = cheminement.ids_cables

    if not ids:
        # L'absence de cable ne se qualifie pas de la meme facon selon la couche
        # et l'etat de coupe-type : la decision est isolee dans sa fonction.
        anomalie = _anomalie_absence_de_cable(cheminement)
        if anomalie is not None:
            anomalies.append(anomalie)
    elif len(ids) > 1:
        anomalies.append(_anomalie_multi_cables(cheminement))

    for id_cable in ids:
        if id_cable not in ids_cables_valides:
            anomalies.append(_anomalie_reference_orpheline(cheminement, id_cable))

    return anomalies


def detecter_anomalies(
    cables: dict[str, EntiteCable],
    cheminements: list[EntiteCheminement],
) -> list[dict[str, Any]]:
    """Detecte toutes les anomalies d'integrite cables/cheminements.

    Applique les quatre regles :
    - Regle 4 : cheminement sans cable ou avec plusieurs cables.
    - Regle 2 : reference cables_href sans cable correspondant.
    - Regles 1 et 3 : cable non reference par aucun cheminement.

    L'ensemble ids_references est construit en une seule passe sur les
    cheminements pour identifier les cables non references en O(n).
    """
    ids_valides = set(cables.keys())  # set pour appartenance en O(1)
    ids_references: set[str] = set()
    anomalies: list[dict[str, Any]] = []
    analyser = _analyser_cheminement  # alias local

    for cheminement in cheminements:
        anomalies.extend(analyser(cheminement, ids_valides))
        for id_cable in cheminement.ids_cables:
            if id_cable in ids_valides:
                ids_references.add(id_cable)

    for id_cable, cable in cables.items():
        if id_cable not in ids_references:
            anomalies.append(_anomalie_cable_non_reference(cable))

    return anomalies


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


# Champs reportes dans les proprietes GeoJSON, par type d'anomalie. Table
# declarative plutot qu'une cascade de if : ajouter un type d'anomalie se fait
# ici seulement, en regard de son constructeur _anomalie_* correspondant.
# L'ordre des champs fixe l'ordre des cles dans le GeoJSON produit.
CHAMPS_PROPRIETES: dict[str, tuple[str, ...]] = {
    "cable_non_reference": ("fichier_cable", "id_cable"),
    "reference_orpheline": ("fichier_cheminement", "id_cheminement", "cables_href_invalide"),
    "cheminement_sans_cable": ("fichier_cheminement", "id_cheminement"),
    "fourreau_sans_cable": ("fichier_cheminement", "id_cheminement", "etat_coupe_type"),
    "cheminement_multi_cables": ("fichier_cheminement", "id_cheminement", "nb_cables", "cables_href"),
}


def _construire_proprietes(anomalie: dict[str, Any]) -> dict[str, Any]:
    """Construit le dictionnaire de proprietes GeoJSON d'une anomalie.

    Les proprietes communes (type_anomalie, priorite) sont toujours presentes.
    Les proprietes specifiques sont celles declarees dans CHAMPS_PROPRIETES
    pour le type d'anomalie ; un type inconnu ne produit que les communes.
    """
    type_anomalie = anomalie["type_anomalie"]

    props: dict[str, Any] = {
        "type_anomalie": type_anomalie,
    }
    for champ in CHAMPS_PROPRIETES.get(type_anomalie, ()):
        props[champ] = anomalie[champ]

    # L'identifiant de cheminement est optionnel en entree mais toujours
    # serialise en chaine dans le GeoJSON, pour un typage stable cote QGIS.
    id_chemin = props.get("id_cheminement")
    if id_chemin is not None:
        props["id_cheminement"] = str(id_chemin)

    return props


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    profil: ProfilEcarts,
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des anomalies d'integrite detectees.

    La geometrie de chaque feature est celle de l'entite concernee (cable
    ou cheminement selon le type d'anomalie), ce qui permet la localisation
    dans QGIS. Le crs est propage depuis les fichiers sources.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": _construire_proprietes(a),
            "geometry": a.get("geometrie"),
        }
        for a in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return normaliser_geojson_ecarts(resultat, profil)


# ---------------------------------------------------------------------------
# Orchestration CLI
# ---------------------------------------------------------------------------


def executer_analyse(
    repertoire: str,
    types_retenus: frozenset[str],
    profil: ProfilEcarts,
    fichier_sortie: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle d'integrite cables/cheminements en mode CLI.

    Charge les entites cables et cheminements, detecte les quatre types
    d'anomalies et ecrit le fichier d'ecarts GeoJSON. Les fichiers absents
    sont listes dans le rapport sans bloquer l'execution.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    cables, fichiers_cables_absents = charger_cables(repertoire_resolu)
    cheminements, fichiers_cheminement_absents, crs = charger_cheminements(repertoire_resolu)

    anomalies = detecter_anomalies(cables, cheminements)
    # Le moteur a releve toutes les anomalies ; le controle appelant ne
    # retient que celles de son code. Les compteurs qui suivent portent donc
    # sur son perimetre, non sur celui du moteur.
    anomalies = filtrer_par_type(anomalies, types_retenus)
    geojson_ecarts = construire_geojson_ecarts(anomalies, profil, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, fichier_sortie)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_anomalies_par_type(anomalies),
        "nombre_cables_analyses": len(cables),
        "nombre_cheminements_analyses": len(cheminements),
        "fichiers_cables_absents": fichiers_cables_absents,
        "fichiers_cheminement_absents": fichiers_cheminement_absents,
        "sortie": chemin_ecrit,
    }
