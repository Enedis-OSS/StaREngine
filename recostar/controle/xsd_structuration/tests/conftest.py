"""
Fixtures partagées pour les tests du contrôle E110.
"""

import os
import sys
from pathlib import Path
from xml.etree.ElementTree import Element  # nosec B405

import pytest

# Accès aux modules du répertoire parent (E110/) et du répertoire courant (tests/)
_tests_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_tests_dir)
sys.path.insert(0, _parent_dir)
sys.path.insert(0, _tests_dir)

from utils_gml import (
    creer_feature_member,
    creer_feature_member_avec_valeurs,
    creer_gml_complet,
    creer_metadata_conforme,
    creer_reseau_utilite_conforme,
    serialiser_gml_avec_entete,
)


@pytest.fixture
def chemin_gml_vide(tmp_path: Path) -> Path:
    """Fichier GML vide temporaire, existant sur disque."""
    chemin = tmp_path / "test.gml"
    chemin.touch()
    return chemin


@pytest.fixture
def chemin_gml_tmp(tmp_path: Path):
    """Retourne une factory créant un fichier GML temporaire à partir d'une liste de membres."""

    def factory(membres: list[Element]) -> Path:
        contenu = creer_gml_complet(membres)
        chemin = tmp_path / "test.gml"
        chemin.write_bytes(contenu)
        return chemin

    return factory


@pytest.fixture
def membre_jonction_conforme():
    """featureMember RPD_Jonction_Reco avec séquence correcte."""
    return creer_feature_member(
        "RPD_Jonction_Reco",
        "jonction_001",
        [
            "reseau",
            "DomaineTension",
            "Geometrie",
            "PrecisionXY",
            "PrecisionZ",
            "Statut",
            "TypeJonction",
        ],
    )


@pytest.fixture
def membre_jonction_ordre_incorrect():
    """featureMember RPD_Jonction_Reco avec conteneur après DomaineTension (hors ordre)."""
    return creer_feature_member(
        "RPD_Jonction_Reco",
        "jonction_002",
        ["reseau", "DomaineTension", "conteneur", "Statut", "TypeJonction"],
    )


@pytest.fixture
def membre_aerien_conforme():
    """featureMember RPD_Aerien_Reco avec séquence correcte."""
    return creer_feature_member(
        "RPD_Aerien_Reco",
        "aerien_001",
        ["reseau", "Geometrie", "ModePose", "PrecisionXY", "PrecisionZ"],
    )


@pytest.fixture
def membre_cable_electrique_conforme():
    """featureMember RPD_CableElectrique_Reco avec séquence correcte (champs optionnels absents)."""
    return creer_feature_member(
        "RPD_CableElectrique_Reco",
        "cable_001",
        ["reseau", "DomaineTension", "FonctionCable", "Statut"],
    )


@pytest.fixture
def membre_ep_ignore():
    """featureMember EP_Coffret_Reco (doit être ignoré lors de la validation)."""
    return creer_feature_member(
        "EP_Coffret_Reco",
        "ep_coffret_001",
        ["reseau", "Geometrie"],
    )


# ---------------------------------------------------------------------------
# Fixtures spécifiques au contrôle E111 (règles métier)
# ---------------------------------------------------------------------------


@pytest.fixture
def membre_cable_elec_en_attente_complet():
    """RPD_CableElectrique_Reco statut « En attente » avec tous les champs métier."""
    return creer_feature_member_avec_valeurs(
        "RPD_CableElectrique_Reco",
        "cable_en_attente_001",
        [
            ("reseau", None),
            ("DomaineTension", "HTA"),
            ("FonctionCable", "DistributionEnergie"),
            ("NombreConducteurs", "3"),
            ("Section", "240"),
            ("Isolant", "Reticulee"),
            ("Materiau", "Alu"),
            ("Statut", "UnderCommissionning"),
        ],
    )


@pytest.fixture
def membre_cable_elec_en_attente_incomplet():
    """RPD_CableElectrique_Reco « En attente » sans Section ni Isolant : règle R001 violée."""
    return creer_feature_member_avec_valeurs(
        "RPD_CableElectrique_Reco",
        "cable_en_attente_002",
        [
            ("reseau", None),
            ("DomaineTension", "HTA"),
            ("FonctionCable", "DistributionEnergie"),
            ("NombreConducteurs", "3"),
            ("Materiau", "Alu"),
            ("Statut", "UnderCommissionning"),
        ],
    )


@pytest.fixture
def membre_cable_elec_bt_sans_hierarchie():
    """RPD_CableElectrique_Reco BT sans HierarchieBT : règle R002 violée."""
    return creer_feature_member_avec_valeurs(
        "RPD_CableElectrique_Reco",
        "cable_bt_001",
        [
            ("reseau", None),
            ("DomaineTension", "BT"),
            ("FonctionCable", "DistributionEnergie"),
            ("Statut", "Functional"),
        ],
    )


# ---------------------------------------------------------------------------
# Fixtures spécifiques au contrôle E113 (en-têtes)
# ---------------------------------------------------------------------------


@pytest.fixture
def chemin_gml_entete_tmp(tmp_path: Path):
    """Factory créant un GML temporaire avec un en-tête contrôlable.

    Tous les paramètres de serialiser_gml_avec_entete sont exposés au test,
    ce qui évite la duplication d'un boilerplate d'écriture fichier.
    """

    def factory(membres: list[Element], **options) -> Path:
        contenu = serialiser_gml_avec_entete(membres, **options)
        chemin = tmp_path / "test_e113.gml"
        chemin.write_bytes(contenu)
        return chemin

    return factory


@pytest.fixture
def membre_metadata_conforme():
    """featureMember Metadata complet (PDF §[3])."""
    return creer_metadata_conforme()


@pytest.fixture
def membre_reseau_utilite_conforme():
    """featureMember ReseauUtilite complet (PDF §9)."""
    return creer_reseau_utilite_conforme()


@pytest.fixture
def gml_entete_conforme(
    chemin_gml_entete_tmp,
    membre_metadata_conforme,
    membre_reseau_utilite_conforme,
):
    """Fichier GML minimal mais conforme à toutes les exigences E113."""
    return chemin_gml_entete_tmp(
        [
            membre_metadata_conforme,
            membre_reseau_utilite_conforme,
        ]
    )
