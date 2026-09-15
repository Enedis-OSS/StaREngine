"""
Moteur de detection : rattachement du materiel a la jonction qui le porte.

Verifie que chaque entite RPD_Materiel_Reco est bien portee par une entite
RPD_Jonction_Reco, et que cette jonction est d'un type susceptible de recevoir
du materiel.

Chaine de references controlee, parcourue **en sens inverse du catalogue de
materiel** :

    RPD_Materiel_Reco.id  <--  RPD_Jonction_Reco.materiel_href

Le catalogue (E-7104, E-9600) part de la jonction et valide les valeurs du
materiel qu'elle designe ; ce moteur part du materiel et valide la jonction qui
le designe. Les deux parcourent la meme relation mais n'ont ni le meme perimetre
ni le meme sujet : un materiel qu'aucune jonction ne reference est invisible du
catalogue, qui ne le rencontre jamais.

Perimetre : **toutes** les entites RPD_Materiel_Reco, sans condition.
RPD_Materiel_Reco ne porte pas de champ Statut, et le perimetre ne depend donc
d'aucun etat. Le statut de la **jonction**, lui, n'est pas un filtre mais une
regle : un materiel porte par une jonction hors UnderCommissionning n'est pas
ignore, il est signale sous E-7103.

Regles de gestion, deux codes du verificateur :
  - jonction_absente        : aucune RPD_Jonction_Reco ne reference ce materiel
                              via materiel_href. Le materiel est orphelin
                              (E-7102) ;
  - type_jonction_invalide  : une jonction le reference, mais son TypeJonction
                              n'est ni Derivation ni Jonction. Seuls ces deux
                              types portent du materiel (cf. le drapeau
                              champsFabricantModele du referentiel
                              referentiels/boites/jonction-mapping.json) ; une
                              ExtremiteReseau ou une RemonteeAeroSouterraine
                              n'a pas de Fabricant ni de Modele a declarer
                              (E-7102) ;
  - statut_jonction_invalide : la jonction est bien une boite, mais son Statut
                              ne vaut pas UnderCommissionning. Le materiel est
                              rattache a un ouvrage qui n'est pas en cours de
                              pose (E-7103).

Les trois sont exclusives et couvrent la relation : un materiel n'a pas de
jonction, ou en a une d'un type inadapte, ou d'un type valide mais hors statut,
ou tout est conforme. La regle de statut n'est evaluee que sur un type valide :
signaler le statut d'une ExtremiteReseau reviendrait a lui reprocher deux fois
de porter du materiel.

Materiel reference par plusieurs jonctions : le cas ne se rencontre pas sur les
jeux de reference, mais rien ne l'interdit structurellement. Une anomalie est
alors emise **par lien fautif**, convention des controles de relation du projet
(E-9500, E-6103, E-9502) : chaque jonction indument rattachee est un defaut a
corriger
pour elle-meme.

Geometrie des ecarts : RPD_Materiel_Reco n'ayant pas de geometrie propre, la
feature d'ecart porte le Point de la jonction en cause. Un materiel orphelin n'a
aucune position connue — ni la sienne, ni celle d'une jonction : sa feature est
ecrite avec une geometrie nulle, ce que le format GeoJSON admet. La signaler
sans position est preferable a lui en inventer une.

Versions : materiel et jonction ont une structure identique en RecoStaR V1.0 et
V1.1 ; le controle est agnostique de version.

Controles issus de ce moteur : e7102, e7103.

Le moteur n'est pas executable : ses deux controles en tiennent lieu.
"""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

# Fichiers source, champs de relation et chargement mutualises avec le catalogue
# de materiel : les deux parcourent la meme relation, en sens opposes.
from recostar.controle.fonctions_communes.chargement import (
    charger_features,
)
from recostar.controle.fonctions_communes.ecarts import filtrer_par_type
from recostar.controle.fonctions_communes.geojson import (
    ProfilEcarts,
    compter_anomalies_par_type,
    ecrire_geojson_si_anomalies,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)
from recostar.controle.fonctions_communes.modele_recostar import (
    FICHIER_JONCTION,
    FICHIER_MATERIEL,
    STATUT_MISE_EN_SERVICE,
)
from recostar.controle.fonctions_communes.modele_recostar import (
    TYPES_JONCTION_AVEC_MATERIEL as TYPES_JONCTION_VALIDES,
)
from recostar.controle.fonctions_communes.relations_jonction import LienJonction, indexer_jonctions_par_materiel

# Types d'anomalie produits par ce controle
TYPE_JONCTION_ABSENTE: str = "jonction_absente"
TYPE_JONCTION_INVALIDE: str = "type_jonction_invalide"
TYPE_STATUT_INVALIDE: str = "statut_jonction_invalide"


# ---------------------------------------------------------------------------
# Regle metier (fonction pure, testable sans I/O)
# ---------------------------------------------------------------------------


def classifier_lien(lien: LienJonction) -> str | None:
    """Retourne le type d'anomalie d'un lien materiel -> jonction, ou None.

    Les deux regles sont evaluees en cascade : un type inadapte court-circuite
    la regle de statut. Reprocher son statut a une ExtremiteReseau reviendrait a
    lui reprocher deux fois de porter du materiel, alors qu'un seul geste — le
    detacher — corrige les deux.
    """
    if not type_jonction_valide(lien.type_jonction):
        return TYPE_JONCTION_INVALIDE
    if lien.statut != STATUT_MISE_EN_SERVICE:
        return TYPE_STATUT_INVALIDE
    return None


def type_jonction_valide(type_jonction: Any) -> bool:
    """Indique si un TypeJonction autorise le port de materiel.

    La comparaison est stricte, sans normalisation : TypeJonction est une
    enumeration du schema XSD et non une saisie libre — meme convention que le
    catalogue de materiel.
    Une valeur absente, vide ou d'une autre casse est donc invalide, et doit
    l'etre : elle ne correspond a aucune valeur du schema.
    """
    return type_jonction in TYPES_JONCTION_VALIDES


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def _anomalie(
    type_anomalie: str,
    id_materiel: str | None,
    lien: LienJonction | None,
) -> dict[str, Any]:
    """Assemble une anomalie ; les valeurs brutes sont conservees pour diagnostic."""
    return {
        "type_anomalie": type_anomalie,
        "id_materiel": id_materiel,
        "id_jonction": lien.id_jonction if lien is not None else None,
        "type_jonction": lien.type_jonction if lien is not None else None,
        "statut_jonction": lien.statut if lien is not None else None,
        "geometrie": lien.geometrie if lien is not None else None,
    }


def detecter_anomalies(
    features_materiel: list[dict[str, Any]],
    liens_par_materiel: Mapping[str, list[LienJonction]],
) -> list[dict[str, Any]]:
    """Detecte les materiels mal rattaches a une jonction.

    Tous les materiels sont parcourus. Un materiel depourvu d'identifiant ne
    peut etre reference par aucune jonction : il est traite comme orphelin, ce
    qu'il est effectivement du point de vue de la relation.
    """
    anomalies: list[dict[str, Any]] = []
    classifier = classifier_lien  # alias local (boucle principale)
    for feature in features_materiel:
        id_materiel = obtenir_id_feature(feature)
        liens = liens_par_materiel.get(id_materiel) if id_materiel is not None else None
        if not liens:
            anomalies.append(_anomalie(TYPE_JONCTION_ABSENTE, id_materiel, None))
            continue
        for lien in liens:
            type_anomalie = classifier(lien)
            if type_anomalie is not None:
                anomalies.append(_anomalie(type_anomalie, id_materiel, lien))
    return anomalies


def compter_liens_controles(
    features_materiel: list[dict[str, Any]],
    liens_par_materiel: Mapping[str, list[LienJonction]],
) -> int:
    """Compte les liens (materiel, jonction) effectivement evalues."""
    return sum(len(liens_par_materiel.get(obtenir_id_feature(feature) or "", ())) for feature in features_materiel)


def compter_materiels_non_conformes(anomalies: list[dict[str, Any]]) -> int:
    """Compte les materiels distincts portant au moins une anomalie."""
    return len({anomalie["id_materiel"] for anomalie in anomalies})


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    profil: ProfilEcarts,
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des materiels mal rattaches.

    La geometrie est celle de la jonction en cause ; elle est nulle pour un
    materiel orphelin, qui n'a aucune position connue. Le crs est propage depuis
    le fichier des jonctions, seul porteur de geometrie des deux sources.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": a["type_anomalie"],
                "fichier_source": FICHIER_MATERIEL,
                "id_materiel": a["id_materiel"],
                "id_jonction": a["id_jonction"],
                "type_jonction": a["type_jonction"],
                "statut_jonction": a["statut_jonction"],
            },
            "geometry": a["geometrie"],
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
    """Execute le controle de rattachement du materiel en mode CLI.

    Indexe les references des jonctions, evalue chaque materiel et ecrit le
    fichier d'ecarts GeoJSON. L'absence d'un fichier source est signalee sans
    bloquer : un fichier jonction absent rend simplement tous les materiels
    orphelins, ce qui est le constat exact.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    features_materiel, _, materiel_absent = charger_features(repertoire_resolu, FICHIER_MATERIEL)
    features_jonction, crs, jonction_absent = charger_features(repertoire_resolu, FICHIER_JONCTION)
    liens_par_materiel = indexer_jonctions_par_materiel(features_jonction)

    anomalies = filtrer_par_type(detecter_anomalies(features_materiel, liens_par_materiel), types_retenus)
    geojson_ecarts = construire_geojson_ecarts(anomalies, profil, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, fichier_sortie)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_anomalies_par_type(anomalies),
        "nombre_materiels_analyses": len(features_materiel),
        "nombre_materiels_non_conformes": compter_materiels_non_conformes(anomalies),
        "nombre_jonctions_analysees": len(features_jonction),
        "nombre_liens_controles": compter_liens_controles(features_materiel, liens_par_materiel),
        "fichier_materiel_absent": materiel_absent,
        "fichier_jonction_absent": jonction_absent,
        "sortie": chemin_ecrit,
    }
