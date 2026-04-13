"""
Tests unitaires du controle altimetrique des sommets (controle_alti_sommets).

Couvre les cas nominaux et les cas limites :
- calcul de l'ecart residuel entre sommets centraux
- logique de la fenetre glissante et exclusion des 3 premiers/derniers sommets
- exclusion des cables references par un cheminement aerien
- construction du GeoJSON de sortie
- execution CLI bout en bout via tmp_path
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from controle_alti_sommets import (
    FICHIER_AERIEN,
    FICHIER_CABLES,
    FICHIER_SORTIE,
    NB_SOMMETS_IGNORES,
    SEUIL_ECART_ALTI,
    TAILLE_FENETRE,
    _analyser_sommets_cable,
    _ecart_residuel_centraux,
    _indices_centraux_valides,
    collecter_ids_cables_aeriens,
    construire_geojson_ecarts,
    controler_altimetrie_sommets,
    executer_controle_cli,
)

# --------------------------------------------------------------------------- #
# Helpers de construction de features GeoJSON pour les tests
# --------------------------------------------------------------------------- #


def _construire_cable(
    identifiant: str, coordonnees: list[list[float]]
) -> dict[str, Any]:
    """Construit une feature cable electrique minimale pour les tests."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant},
        "geometry": {"type": "LineString", "coordinates": coordonnees},
    }


def _construire_aerien(identifiant: str, cables_href: Any) -> dict[str, Any]:
    """Construit une feature aerienne minimale referencant un ou plusieurs cables."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant, "cables_href": cables_href},
        "geometry": {"type": "LineString", "coordinates": [[0, 0, 0], [1, 1, 0]]},
    }


def _ligne_plate(nb_sommets: int) -> list[list[float]]:
    """Genere une ligne horizontale strictement plate en altimetrie."""
    return [[float(i), 0.0, 10.0] for i in range(nb_sommets)]


# --------------------------------------------------------------------------- #
# Tests des fonctions unitaires
# --------------------------------------------------------------------------- #


class TestEcartResiduel:
    """Tests unitaires du calcul de l'ecart residuel sur une fenetre de 4 sommets."""

    def test_ligne_parfaitement_plate_retourne_zero(self) -> None:
        fenetre = [[0, 0, 10], [1, 0, 10], [2, 0, 10], [3, 0, 10]]
        assert _ecart_residuel_centraux(fenetre) == pytest.approx(0.0)

    def test_pente_reguliere_retourne_zero(self) -> None:
        # Pente lineaire reguliere : la tendance compense exactement l'ecart brut
        fenetre = [[0, 0, 10], [1, 0, 11], [2, 0, 12], [3, 0, 13]]
        assert _ecart_residuel_centraux(fenetre) == pytest.approx(0.0)

    def test_pic_altimetrique_detecte(self) -> None:
        # Le second sommet central forme un pic de 1 metre par rapport a la tendance
        fenetre = [[0, 0, 10], [1, 0, 10], [2, 0, 11], [3, 0, 10]]
        assert _ecart_residuel_centraux(fenetre) == pytest.approx(1.0)

    def test_fenetre_degeneree_utilise_ecart_brut(self) -> None:
        # Tous les sommets ont les memes coordonnees XY : aucune tendance exploitable
        fenetre = [[5, 5, 10], [5, 5, 10.5], [5, 5, 11.0], [5, 5, 10]]
        assert _ecart_residuel_centraux(fenetre) == pytest.approx(0.5)


class TestIndicesCentraux:
    """Tests de la plage des indices de fenetres analysables."""

    def test_cable_trop_court_ne_produit_aucune_fenetre(self) -> None:
        # Avec 3 sommets ignores de chaque cote, il faut au moins 8 sommets
        for nb in range(0, 8):
            assert len(list(_indices_centraux_valides(nb))) == 0

    def test_cable_de_huit_sommets_produit_une_seule_fenetre(self) -> None:
        indices = list(_indices_centraux_valides(8))
        assert indices == [2]

    def test_cable_de_dix_sommets_produit_trois_fenetres(self) -> None:
        indices = list(_indices_centraux_valides(10))
        assert indices == [2, 3, 4]


class TestAnalyseSommets:
    """Tests de l'analyse altimetrique d'un cable complet."""

    def test_cable_plat_sans_anomalie(self) -> None:
        coordonnees = _ligne_plate(12)
        assert _analyser_sommets_cable(coordonnees) == {}

    def test_anomalie_au_centre_detectee(self) -> None:
        coordonnees = _ligne_plate(12)
        # Creation d'un pic franc de 1 metre sur le sommet central
        coordonnees[6][2] = 11.0
        anomalies = _analyser_sommets_cable(coordonnees)
        assert 6 in anomalies
        assert anomalies[6] > SEUIL_ECART_ALTI

    def test_sommets_ignores_ne_sont_jamais_signales(self) -> None:
        # Un pic situe dans la zone ignoree ne doit pas etre detecte
        coordonnees = _ligne_plate(12)
        for indice_ignore in (0, 1, 2, 9, 10, 11):
            coordonnees_test = [list(point) for point in coordonnees]
            coordonnees_test[indice_ignore][2] = 15.0
            anomalies = _analyser_sommets_cable(coordonnees_test)
            indices_ignores = set(range(NB_SOMMETS_IGNORES)) | set(
                range(len(coordonnees_test) - NB_SOMMETS_IGNORES, len(coordonnees_test))
            )
            assert indices_ignores.isdisjoint(anomalies.keys())

    def test_ecart_sous_seuil_ignore(self) -> None:
        coordonnees = _ligne_plate(12)
        # 10 cm : strictement inferieur au seuil de 25 cm
        coordonnees[6][2] = 10.10
        assert _analyser_sommets_cable(coordonnees) == {}


class TestCollecteIdsAeriens:
    """Tests de la normalisation du champ cables_href."""

    def test_reference_simple_sous_forme_chaine(self) -> None:
        features = [_construire_aerien("a1", "cable-1")]
        assert collecter_ids_cables_aeriens(features) == {"cable-1"}

    def test_reference_liste_multiple(self) -> None:
        features = [_construire_aerien("a1", ["cable-1", "cable-2"])]
        assert collecter_ids_cables_aeriens(features) == {"cable-1", "cable-2"}

    def test_references_multiples_dans_une_chaine(self) -> None:
        features = [_construire_aerien("a1", "cable-1 cable-2")]
        assert collecter_ids_cables_aeriens(features) == {"cable-1", "cable-2"}

    def test_aucune_reference(self) -> None:
        assert collecter_ids_cables_aeriens([]) == set()


class TestControleAltimetrie:
    """Tests d'integration du controle altimetrique sur une collection de cables."""

    def test_cable_aerien_est_exclu(self) -> None:
        coordonnees = _ligne_plate(12)
        coordonnees[6][2] = 15.0
        cables = [_construire_cable("cable-aerien", coordonnees)]
        anomalies = controler_altimetrie_sommets(cables, {"cable-aerien"})
        assert anomalies == []

    def test_cable_avec_anomalie_produit_un_resultat(self) -> None:
        coordonnees = _ligne_plate(12)
        coordonnees[6][2] = 15.0
        cables = [_construire_cable("cable-sol", coordonnees)]
        anomalies = controler_altimetrie_sommets(cables, set())
        # Les deux sommets centraux de la fenetre autour du pic sont signales
        assert len(anomalies) >= 1
        assert all(a["id_cable"] == "cable-sol" for a in anomalies)
        assert all(a["ecart_residuel"] > SEUIL_ECART_ALTI for a in anomalies)

    def test_cable_sans_coordonnees_z_est_ignore(self) -> None:
        coordonnees = [[float(i), 0.0] for i in range(12)]
        cables = [_construire_cable("cable-2d", coordonnees)]
        assert controler_altimetrie_sommets(cables, set()) == []

    def test_cable_trop_court_est_ignore(self) -> None:
        cables = [_construire_cable("cable-court", _ligne_plate(TAILLE_FENETRE - 1))]
        assert controler_altimetrie_sommets(cables, set()) == []


class TestGeojsonSortie:
    """Tests de la serialisation des anomalies en FeatureCollection."""

    def test_structure_geojson_conforme(self) -> None:
        anomalies = [
            {
                "id_cable": "c1",
                "indice_sommet": 5,
                "coordonnees": [1.0, 2.0, 3.0],
                "ecart_residuel": 0.42,
            }
        ]
        geojson = construire_geojson_ecarts(anomalies)
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 1
        feature = geojson["features"][0]
        assert feature["geometry"] == {"type": "Point", "coordinates": [1.0, 2.0, 3.0]}
        assert feature["properties"]["id_cable"] == "c1"
        assert feature["properties"]["indice_sommet"] == 5
        assert feature["properties"]["ecart_residuel_m"] == pytest.approx(0.42)
        assert feature["properties"]["priorite"] == "bloquant"

    def test_feature_collection_vide(self) -> None:
        geojson = construire_geojson_ecarts([])
        assert geojson == {"type": "FeatureCollection", "features": []}

    def test_crs_propage_si_present(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        geojson = construire_geojson_ecarts([], crs=crs)
        assert geojson["crs"] == crs

    def test_crs_absent_si_non_fourni(self) -> None:
        geojson = construire_geojson_ecarts([])
        assert "crs" not in geojson


# --------------------------------------------------------------------------- #
# Tests CLI bout en bout
# --------------------------------------------------------------------------- #


@pytest.fixture
def repertoire_test(tmp_path: Any) -> str:
    """Prepare un repertoire avec cables et donnees aerien."""
    coordonnees_anomalie = _ligne_plate(12)
    coordonnees_anomalie[6][2] = 15.0

    cables_collection = {
        "type": "FeatureCollection",
        "features": [
            _construire_cable("cable-sol", coordonnees_anomalie),
            _construire_cable("cable-aerien-ref", _ligne_plate(12)),
        ],
    }
    aerien_collection = {
        "type": "FeatureCollection",
        "features": [_construire_aerien("aerien-1", "cable-aerien-ref")],
    }

    (tmp_path / FICHIER_CABLES).write_text(
        json.dumps(cables_collection), encoding="utf-8"
    )
    (tmp_path / FICHIER_AERIEN).write_text(
        json.dumps(aerien_collection), encoding="utf-8"
    )
    return str(tmp_path)


class TestCli:
    """Tests d'integration de l'interface CLI."""

    def test_execution_ecrit_fichier_sortie(self, repertoire_test: str) -> None:
        resultat = executer_controle_cli(repertoire_test)
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] >= 1
        assert resultat["cables_exclus"] == 1
        chemin_sortie = os.path.join(repertoire_test, FICHIER_SORTIE)
        assert os.path.isfile(chemin_sortie)
        with open(chemin_sortie, "r", encoding="utf-8") as fichier:
            contenu = json.load(fichier)
        assert contenu["type"] == "FeatureCollection"
        assert len(contenu["features"]) >= 1

    def test_repertoire_sortie_distinct(
        self, repertoire_test: str, tmp_path: Any
    ) -> None:
        dossier_sortie = tmp_path / "sortie"
        resultat = executer_controle_cli(repertoire_test, str(dossier_sortie))
        assert resultat["succes"] is True
        assert os.path.isfile(os.path.join(str(dossier_sortie), FICHIER_SORTIE))

    def test_repertoire_inexistant_retourne_erreur(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path / "inexistant"))
        assert resultat["succes"] is False
        assert "erreur" in resultat
