"""
Controle E601 : rattachement du materiel a une jonction de type valide.

Verifie que chaque entite RPD_Materiel_Reco est bien portee par une entite
RPD_Jonction_Reco, et que cette jonction est d'un type susceptible de recevoir
du materiel.

Chaine de references controlee, parcourue **en sens inverse d'E600** :

    RPD_Materiel_Reco.id  <--  RPD_Jonction_Reco.materiel_href

E600 part de la jonction et valide les valeurs du materiel qu'elle designe ;
E601 part du materiel et valide la jonction qui le designe. Les deux controles
partagent la meme relation mais n'ont ni le meme perimetre ni le meme sujet :
un materiel qu'aucune jonction ne reference est invisible d'E600, qui ne le
rencontre jamais.

Perimetre : **toutes** les entites RPD_Materiel_Reco, sans condition. A la
difference d'E600, aucun filtre de statut ne s'applique : RPD_Materiel_Reco ne
porte pas de champ Statut, et la regle ne subordonne le rattachement a aucun
etat de la jonction. Un materiel porte par une jonction Decommissioned reste
donc conforme si le type de celle-ci est valide.

Regles de gestion :
  - jonction_absente        : aucune RPD_Jonction_Reco ne reference ce materiel
                              via materiel_href. Le materiel est orphelin ;
  - type_jonction_invalide  : une jonction le reference, mais son TypeJonction
                              n'est ni Derivation ni Jonction. Seuls ces deux
                              types portent du materiel (cf. le drapeau
                              champsFabricantModele du referentiel
                              referentiels/boites/jonction-mapping.json) ; une
                              ExtremiteReseau ou une RemonteeAeroSouterraine
                              n'a pas de Fabricant ni de Modele a declarer.

Materiel reference par plusieurs jonctions : le cas ne se rencontre pas sur les
jeux de reference, mais rien ne l'interdit structurellement. Une anomalie est
alors emise **par lien fautif**, convention des controles de relation du projet
(E500, E503, E507) : chaque jonction indument rattachee est un defaut a corriger
pour elle-meme.

Geometrie des ecarts : RPD_Materiel_Reco n'ayant pas de geometrie propre, la
feature d'ecart porte le Point de la jonction en cause. Un materiel orphelin n'a
aucune position connue — ni la sienne, ni celle d'une jonction : sa feature est
ecrite avec une geometrie nulle, ce que le format GeoJSON admet. La signaler
sans position est preferable a lui en inventer une.

Versions : materiel et jonction ont une structure identique en RecoStaR V1.0 et
V1.1 ; le controle est agnostique de version.

Usage CLI :
    python controle_e601.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e601_materiel_jonction_non_rattache.geojson
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Fichiers source, champs de relation et chargement mutualises avec E600 : les
# deux controles parcourent la meme relation, en sens opposes. Reutilisation
# inter-controles conforme a l'usage du projet (E505 <- E504, E507 <- E506).
from controle_e600 import (
    CHAMP_MATERIEL_HREF,
    CHAMP_TYPE_JONCTION,
    FICHIER_JONCTION,
    FICHIER_MATERIEL,
    _charger_features,
    normaliser_valeur,
)
from controle_e600 import TYPES_JONCTION_CONTROLES as TYPES_JONCTION_VALIDES
from utils_geojson import (
    ProfilEcarts,
    compter_anomalies_par_type,
    ecrire_geojson_si_anomalies,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e601_materiel_jonction_non_rattache.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E601"

# Types d'anomalie produits par ce controle
TYPE_JONCTION_ABSENTE: str = "jonction_absente"
TYPE_JONCTION_INVALIDE: str = "type_jonction_invalide"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    TYPE_JONCTION_ABSENTE: ("Le matériel n'est rattaché à aucune jonction."),
    TYPE_JONCTION_INVALIDE: ("Le TypeJonction de la jonction portant le matériel n'est ni Derivation ni Jonction."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_materiel", "id_jonction"),
)

# Niveau de priorite affecte a toutes les anomalies. Bloquant : un materiel
# orphelin ou porte par une jonction inapte rompt l'integrite de la relation
# Ouvrage_Materiel, sans laquelle le recolement ne decrit plus quel materiel est
# pose ou (cf. PRIORITES_DECLASSANTES dans synthese_controles).
PRIORITE_ANOMALIE: str = "bloquant"


@dataclass(frozen=True, slots=True)
class LienJonction:
    """Reference d'une jonction vers un materiel, telle qu'indexee.

    Conserve ce dont l'anomalie a besoin — l'identite de la jonction, son type
    brut et sa geometrie — sans retenir la feature entiere.
    """

    id_jonction: str | None
    type_jonction: Any
    geometrie: dict[str, Any] | None


# ---------------------------------------------------------------------------
# Index inverse jonction -> materiel
# ---------------------------------------------------------------------------


def indexer_jonctions_par_materiel(
    features_jonction: list[dict[str, Any]],
) -> dict[str, list[LienJonction]]:
    """Construit l'index {id_materiel: [jonctions le referencant]}.

    C'est l'inverse de l'index d'E600 : la relation n'est portee que par la
    jonction, il faut donc la retourner pour interroger le materiel en O(1).
    Une liste est conservee par materiel — et non un lien unique — afin qu'un
    materiel reference plusieurs fois soit evalue sur chacun de ses liens.

    Les jonctions sans materiel_href sont ignorees : elles ne participent pas a
    la relation. Le href est normalise comme cote E600 (espaces de bord
    supprimes) pour que les deux controles resolvent le meme lien.
    """
    index: defaultdict[str, list[LienJonction]] = defaultdict(list)
    for feature in features_jonction:
        proprietes = feature.get("properties") or {}
        reference = proprietes.get(CHAMP_MATERIEL_HREF)
        if normaliser_valeur(reference) is None:
            continue
        index[str(reference).strip()].append(
            LienJonction(
                obtenir_id_feature(feature),
                proprietes.get(CHAMP_TYPE_JONCTION),
                feature.get("geometry"),
            )
        )
    return dict(index)


# ---------------------------------------------------------------------------
# Regle metier (fonction pure, testable sans I/O)
# ---------------------------------------------------------------------------


def type_jonction_valide(type_jonction: Any) -> bool:
    """Indique si un TypeJonction autorise le port de materiel.

    La comparaison est stricte, sans normalisation : TypeJonction est une
    enumeration du schema XSD et non une saisie libre — meme convention qu'E600.
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
    est_valide = type_jonction_valide  # alias local (boucle principale)
    for feature in features_materiel:
        id_materiel = obtenir_id_feature(feature)
        liens = liens_par_materiel.get(id_materiel) if id_materiel is not None else None
        if not liens:
            anomalies.append(_anomalie(TYPE_JONCTION_ABSENTE, id_materiel, None))
            continue
        anomalies.extend(
            _anomalie(TYPE_JONCTION_INVALIDE, id_materiel, lien) for lien in liens if not est_valide(lien.type_jonction)
        )
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
                "priorite": PRIORITE_ANOMALIE,
            },
            "geometry": a["geometrie"],
        }
        for a in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return normaliser_geojson_ecarts(resultat, PROFIL_ECARTS)


# ---------------------------------------------------------------------------
# Orchestration CLI
# ---------------------------------------------------------------------------


def executer_controle_cli(
    repertoire: str,
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

    features_materiel, _, materiel_absent = _charger_features(repertoire_resolu, FICHIER_MATERIEL)
    features_jonction, crs, jonction_absent = _charger_features(repertoire_resolu, FICHIER_JONCTION)
    liens_par_materiel = indexer_jonctions_par_materiel(features_jonction)

    anomalies = detecter_anomalies(features_materiel, liens_par_materiel)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
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


def main() -> None:
    """Point d'entree CLI du controle de rattachement du materiel."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E601 : rattachement de chaque RPD_Materiel_Reco a une "
            "RPD_Jonction_Reco de TypeJonction Derivation ou Jonction."
        )
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant les fichiers GeoJSON",
    )
    parseur.add_argument(
        "--sortie",
        default=None,
        help="Repertoire de sortie (defaut : meme repertoire que l'entree)",
    )
    arguments = parseur.parse_args()
    resultat = executer_controle_cli(arguments.repertoire, arguments.sortie)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
