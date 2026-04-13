"""
Fixtures partagees pour les tests des traitements RecoStaR.
Fournit des structures GeoJSON de test et des repertoires temporaires.
"""

import json
import os

import pytest


@pytest.fixture
def dossier_projet(tmp_path):
    """Cree un dossier projet temporaire avec la structure recolement/ et rapport/."""
    dossier_recolement = tmp_path / "recolement"
    dossier_recolement.mkdir()
    dossier_rapport = tmp_path / "rapport"
    dossier_rapport.mkdir()
    return tmp_path


@pytest.fixture
def ecrire_geojson():
    """Retourne une fonction utilitaire pour ecrire un fichier GeoJSON."""

    def _ecrire(chemin_dossier, nom_fichier, features):
        collection = {"type": "FeatureCollection", "features": features}
        chemin = os.path.join(str(chemin_dossier), nom_fichier)
        with open(chemin, "w", encoding="utf-8") as fichier:
            json.dump(collection, fichier, ensure_ascii=False)

    return _ecrire


# --- Cables de test ---


@pytest.fixture
def cable_hta_3d():
    """Cable HTA avec geometrie 3D (3 sommets)."""
    return {
        "type": "Feature",
        "properties": {"id": "cable_hta_1", "DomaineTension": "HTA"},
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [100.0, 200.0, 10.0],
                [103.0, 204.0, 13.0],
                [106.0, 208.0, 10.0],
            ],
        },
    }


@pytest.fixture
def cable_bt_3d():
    """Cable BT avec geometrie 3D (2 sommets)."""
    return {
        "type": "Feature",
        "properties": {"id": "cable_bt_1", "DomaineTension": "BT"},
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [100.0, 200.0, 5.0],
                [110.0, 210.0, 8.0],
            ],
        },
    }


@pytest.fixture
def cable_2d():
    """Cable sans coordonnee Z."""
    return {
        "type": "Feature",
        "properties": {"id": "cable_2d", "DomaineTension": "BT"},
        "geometry": {
            "type": "LineString",
            "coordinates": [[100.0, 200.0], [103.0, 204.0]],
        },
    }


# --- Jonctions de test ---


@pytest.fixture
def jonction_ras_depart():
    """Jonction RAS a proximite du depart du cable HTA."""
    return {
        "type": "Feature",
        "properties": {
            "id": "jonc_ras_1",
            "TypeJonction": "RemonteeAeroSouterraine",
            "DomaineTension": "HTA",
            "cables_href": "cable_hta_1",
        },
        "geometry": {"type": "Point", "coordinates": [100.0, 200.0, 10.0]},
    }


@pytest.fixture
def jonction_derivation():
    """Jonction de type Derivation (pas de correction)."""
    return {
        "type": "Feature",
        "properties": {
            "id": "jonc_deriv_1",
            "TypeJonction": "Derivation",
            "DomaineTension": "HTA",
            "cables_href": "cable_hta_1",
        },
        "geometry": {"type": "Point", "coordinates": [106.0, 208.0, 10.0]},
    }


@pytest.fixture
def jonction_ras_bt():
    """Jonction RAS pour cable BT."""
    return {
        "type": "Feature",
        "properties": {
            "id": "jonc_ras_bt",
            "TypeJonction": "RemonteeAeroSouterraine",
            "DomaineTension": "BT",
            "cables_href": "cable_bt_1",
        },
        "geometry": {"type": "Point", "coordinates": [100.0, 200.0, 5.0]},
    }


# --- Postes de test ---


@pytest.fixture
def poste_hta():
    """Poste electrique HTA relie au cable HTA (geometrie polygone)."""
    return {
        "type": "Feature",
        "properties": {
            "id": "poste_1",
            "cables_href": "cable_hta_1",
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [105.0, 207.0],
                    [107.0, 207.0],
                    [107.0, 209.0],
                    [105.0, 209.0],
                    [105.0, 207.0],
                ]
            ],
        },
    }


@pytest.fixture
def poste_bt():
    """Poste electrique relie au cable BT."""
    return {
        "type": "Feature",
        "properties": {
            "id": "poste_bt",
            "cables_href": "cable_bt_1",
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [109.0, 209.0],
                    [111.0, 209.0],
                    [111.0, 211.0],
                    [109.0, 211.0],
                    [109.0, 209.0],
                ]
            ],
        },
    }


# --- Noeuds coffrets de test ---


@pytest.fixture
def noeud_coffret_bt():
    """Noeud de coffret (coupe-circuit) relie au cable BT."""
    return {
        "type": "Feature",
        "properties": {
            "id": "ccf_1",
            "conteneur_href": "coffret_1",
            "cables_href": "cable_bt_1",
        },
        "geometry": {"type": "Point", "coordinates": [110.0, 210.0, 8.0]},
    }


@pytest.fixture
def noeud_sans_conteneur():
    """Noeud sans conteneur_href (ne doit pas etre pris en compte)."""
    return {
        "type": "Feature",
        "properties": {
            "id": "ccf_orphelin",
            "cables_href": "cable_bt_1",
        },
        "geometry": {"type": "Point", "coordinates": [110.0, 210.0, 8.0]},
    }
