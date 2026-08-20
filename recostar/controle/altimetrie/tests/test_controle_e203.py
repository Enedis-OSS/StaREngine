"""
Tests unitaires du controle altimetrique IGN (controle_e203).

Couvre les cas nominaux et les cas limites :
- conversion Lambert 93 vers WGS84
- extraction des sommets 3D depuis differents types de geometrie
- comparaison des altitudes avec seuil de 40 cm
- construction du GeoJSON de sortie
- gestion du fallback entre sources IGN
- decoupage en lots pour l'API
- execution CLI bout en bout via tmp_path (API mockee)
"""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from controle_e203 import (
    CHAMP_STATUT,
    FICHIER_SORTIE,
    FICHIER_SOURCE,
    SEUIL_ECART,
    SOURCES_IGN,
    VALEUR_STATUT_V1_1,
    _aplatir_anneaux,
    _aplatir_polygones,
    _decouper_lots,
    _extraire_altitudes_reponse,
    comparer_altitudes,
    construire_geojson_ecarts,
    convertir_lambert93_vers_wgs84,
    convertir_sommets_wgs84,
    determiner_version_effective,
    executer_controle_cli,
    extraire_sommets,
    filtrer_features_selon_statut,
    recuperer_altitudes_ign,
)
from controle_e204 import FICHIER_DETECTION_VERSION
from utils_tests import (
    construire_feature,
    construire_feature_avec_proprietes,
    ecrire_collection,
    reponse_api_mock,
)

# --------------------------------------------------------------------------- #
# Tests de la conversion Lambert 93 -> WGS84
# --------------------------------------------------------------------------- #


class TestConversionLambert93:
    """Tests de la conversion de coordonnees."""

    def test_point_connu_paris(self) -> None:
        lon, lat = convertir_lambert93_vers_wgs84(652000.0, 6862000.0)
        assert lon == pytest.approx(2.35, abs=0.1)
        assert lat == pytest.approx(48.86, abs=0.1)

    def test_point_connu_toulouse(self) -> None:
        lon, lat = convertir_lambert93_vers_wgs84(574000.0, 6280000.0)
        assert lon == pytest.approx(1.44, abs=0.1)
        assert lat == pytest.approx(43.60, abs=0.1)

    def test_retourne_tuple_deux_float(self) -> None:
        resultat = convertir_lambert93_vers_wgs84(700000.0, 6600000.0)
        assert isinstance(resultat, tuple)
        assert len(resultat) == 2


# --------------------------------------------------------------------------- #
# Tests de l'extraction des sommets
# --------------------------------------------------------------------------- #


class TestAplatirGeometries:
    """Tests des fonctions d'aplatissement des geometries."""

    def test_aplatir_anneaux(self) -> None:
        anneaux = [[[0, 0, 10], [1, 0, 10], [1, 1, 10], [0, 0, 10]]]
        resultat = _aplatir_anneaux(anneaux)
        assert len(resultat) == 4
        assert resultat[0] == (0, [0, 0, 10])
        assert resultat[3] == (3, [0, 0, 10])

    def test_aplatir_polygones(self) -> None:
        anneau = [[0, 0, 10], [1, 0, 10], [1, 1, 10], [0, 0, 10]]
        polygones = [[anneau]]
        resultat = _aplatir_polygones(polygones)
        assert len(resultat) == 4


class TestExtraireSommets:
    """Tests de l'extraction des sommets 3D depuis une collection."""

    def test_multipolygon_3d(self) -> None:
        anneau = [
            [850052.0, 6799805.0, 310.0],
            [850053.0, 6799806.0, 311.0],
            [850054.0, 6799805.0, 310.5],
            [850052.0, 6799805.0, 310.0],
        ]
        feature = construire_feature("e1", "MultiPolygon", [[anneau]])
        sommets = extraire_sommets([feature])
        assert len(sommets) == 4
        assert all(s["id_entite"] == "e1" for s in sommets)
        assert all(s["type_geometrie"] == "MultiPolygon" for s in sommets)

    def test_point_3d(self) -> None:
        feature = construire_feature("p1", "Point", [1.0, 2.0, 3.0])
        sommets = extraire_sommets([feature])
        assert len(sommets) == 1
        assert sommets[0]["coordonnees"] == [1.0, 2.0, 3.0]

    def test_point_2d_ignore(self) -> None:
        feature = construire_feature("p1", "Point", [1.0, 2.0])
        sommets = extraire_sommets([feature])
        assert sommets == []

    def test_geometrie_nulle_ignoree(self) -> None:
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {"id": "e1"},
            "geometry": None,
        }
        sommets = extraire_sommets([feature])
        assert sommets == []

    def test_collection_vide(self) -> None:
        assert extraire_sommets([]) == []


class TestConvertirSommetsWgs84:
    """Tests de la conversion en lot des sommets."""

    def test_conversion_retourne_meme_nombre(self) -> None:
        sommets = [
            {"coordonnees": [850052.0, 6799805.0, 310.0]},
            {"coordonnees": [850053.0, 6799806.0, 311.0]},
        ]
        resultat = convertir_sommets_wgs84(sommets)
        assert len(resultat) == 2
        assert all(isinstance(pt, tuple) and len(pt) == 2 for pt in resultat)


# --------------------------------------------------------------------------- #
# Tests de la reponse API IGN
# --------------------------------------------------------------------------- #


class TestExtraireAltitudesReponse:
    """Tests de l'extraction des altitudes depuis la reponse API."""

    def test_altitudes_valides(self) -> None:
        elevations = reponse_api_mock([100.5, 200.3, 150.0])
        alts, valide = _extraire_altitudes_reponse(elevations)
        assert alts == [100.5, 200.3, 150.0]
        assert valide is True

    def test_altitude_sentinelle_ignoree(self) -> None:
        elevations = reponse_api_mock([100.5, -99999.0])
        alts, valide = _extraire_altitudes_reponse(elevations)
        assert alts == [100.5, None]
        assert valide is True

    def test_toutes_sentinelles(self) -> None:
        elevations = reponse_api_mock([-99999.0, -99999.0])
        alts, valide = _extraire_altitudes_reponse(elevations)
        assert all(a is None for a in alts)
        assert valide is False

    def test_liste_vide(self) -> None:
        alts, valide = _extraire_altitudes_reponse([])
        assert alts == []
        assert valide is False


# --------------------------------------------------------------------------- #
# Tests du decoupage en lots
# --------------------------------------------------------------------------- #


class TestDecouperLots:
    """Tests du decoupage en lots de taille fixe."""

    def test_lot_exact(self) -> None:
        lots = list(_decouper_lots([1, 2, 3, 4], 2))
        assert lots == [[1, 2], [3, 4]]

    def test_lot_avec_reste(self) -> None:
        lots = list(_decouper_lots([1, 2, 3], 2))
        assert lots == [[1, 2], [3]]

    def test_lot_unique(self) -> None:
        lots = list(_decouper_lots([1, 2], 10))
        assert lots == [[1, 2]]

    def test_sequence_vide(self) -> None:
        lots = list(_decouper_lots([], 5))
        assert lots == []


# --------------------------------------------------------------------------- #
# Tests de la comparaison des altitudes
# --------------------------------------------------------------------------- #


class TestComparerAltitudes:
    """Tests de la comparaison des altitudes geojson/IGN."""

    def test_ecart_superieur_au_seuil_detecte(self) -> None:
        sommets = [
            {
                "id_entite": "e1",
                "type_geometrie": "Point",
                "indice_sommet": 0,
                "coordonnees": [1.0, 2.0, 10.0],
            }
        ]
        altitudes_ign: list[float | None] = [10.5]
        anomalies = comparer_altitudes(sommets, altitudes_ign, "LIDAR HD IGN")
        assert len(anomalies) == 1
        assert anomalies[0]["ecart_m"] == pytest.approx(0.5, abs=0.001)

    def test_ecart_inferieur_au_seuil_ignore(self) -> None:
        sommets = [
            {
                "id_entite": "e1",
                "type_geometrie": "Point",
                "indice_sommet": 0,
                "coordonnees": [1.0, 2.0, 10.0],
            }
        ]
        altitudes_ign: list[float | None] = [10.2]
        anomalies = comparer_altitudes(sommets, altitudes_ign, "LIDAR HD IGN")
        assert anomalies == []

    def test_altitude_ign_none_ignoree(self) -> None:
        sommets = [
            {
                "id_entite": "e1",
                "type_geometrie": "Point",
                "indice_sommet": 0,
                "coordonnees": [1.0, 2.0, 10.0],
            }
        ]
        altitudes_ign: list[float | None] = [None]
        anomalies = comparer_altitudes(sommets, altitudes_ign, "LIDAR HD IGN")
        assert anomalies == []

    def test_ecart_exact_au_seuil_ignore(self) -> None:
        sommets = [
            {
                "id_entite": "e1",
                "type_geometrie": "Point",
                "indice_sommet": 0,
                "coordonnees": [1.0, 2.0, 10.0],
            }
        ]
        altitudes_ign: list[float | None] = [10.0 + SEUIL_ECART - 0.001]
        anomalies = comparer_altitudes(sommets, altitudes_ign, "LIDAR HD IGN")
        assert anomalies == []

    def test_attributs_anomalie_complets(self) -> None:
        sommets = [
            {
                "id_entite": "e1",
                "type_geometrie": "MultiPolygon",
                "indice_sommet": 3,
                "coordonnees": [850052.0, 6799805.0, 310.0],
            }
        ]
        altitudes_ign: list[float | None] = [311.0]
        anomalies = comparer_altitudes(sommets, altitudes_ign, "LIDAR HD IGN")
        assert len(anomalies) == 1
        a = anomalies[0]
        assert a["id_entite"] == "e1"
        assert a["type_geometrie"] == "MultiPolygon"
        assert a["indice_sommet"] == 3
        assert a["altitude_geojson"] == pytest.approx(310.0)
        assert a["altitude_ign"] == pytest.approx(311.0)
        assert a["ecart_m"] == pytest.approx(1.0)
        assert a["source_ign"] == "LIDAR HD IGN"


# --------------------------------------------------------------------------- #
# Tests du GeoJSON de sortie
# --------------------------------------------------------------------------- #


class TestGeojsonSortie:
    """Tests de la serialisation des anomalies en FeatureCollection."""

    def test_structure_conforme(self) -> None:
        anomalies = [
            {
                "id_entite": "e1",
                "type_geometrie": "MultiPolygon",
                "indice_sommet": 0,
                "coordonnees": [1.0, 2.0, 10.0],
                "altitude_geojson": 10.0,
                "altitude_ign": 11.0,
                "ecart_m": 1.0,
                "source_ign": "LIDAR HD IGN",
            }
        ]
        geojson = construire_geojson_ecarts(anomalies)
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 1

        f = geojson["features"][0]
        assert f["geometry"] == {"type": "Point", "coordinates": [1.0, 2.0, 10.0]}
        props = f["properties"]
        assert props["priorite"] == "information"
        assert props["type_anomalie"] == "ecart_altimetrique_ign"
        assert props["seuil_m"] == SEUIL_ECART

    def test_collection_vide(self) -> None:
        geojson = construire_geojson_ecarts([])
        assert geojson == {"type": "FeatureCollection", "features": []}

    def test_crs_propage_si_present(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        geojson = construire_geojson_ecarts([], crs=crs)
        assert geojson["crs"] == crs

    def test_crs_absent_si_non_fourni(self) -> None:
        geojson = construire_geojson_ecarts([])
        assert "crs" not in geojson


class TestRecupererAltitudesIgn:
    """Tests de la recuperation des altitudes IGN avec API mockee."""

    @patch("controle_e203._requeter_api_ign")
    def test_source_primaire_ok(self, mock_api: MagicMock) -> None:
        mock_api.return_value = reponse_api_mock([100.0, 200.0])
        points = [(2.35, 48.86), (2.36, 48.87)]

        alts, source = recuperer_altitudes_ign(points)
        assert alts == [100.0, 200.0]
        assert source == SOURCES_IGN[0][1]
        assert mock_api.call_count == 1

    @patch("controle_e203._requeter_api_ign")
    def test_fallback_source_secondaire(self, mock_api: MagicMock) -> None:
        mock_api.side_effect = [None, reponse_api_mock([100.0, 200.0])]
        points = [(2.35, 48.86), (2.36, 48.87)]

        alts, source = recuperer_altitudes_ign(points)
        assert alts == [100.0, 200.0]
        assert source == SOURCES_IGN[1][1]

    @patch("controle_e203._requeter_api_ign")
    def test_toutes_sources_echouent(self, mock_api: MagicMock) -> None:
        mock_api.return_value = None
        points = [(2.35, 48.86)]

        alts, source = recuperer_altitudes_ign(points)
        assert all(a is None for a in alts)
        assert source == ""


# --------------------------------------------------------------------------- #
# Tests CLI bout en bout avec tmp_path et API mockee
# --------------------------------------------------------------------------- #


@pytest.fixture
def repertoire_test(tmp_path: Any) -> str:
    """Prepare un repertoire contenant un fichier GeometrieSupplementaire.

    L'entite porte un Statut UnderCommissionning : elle est donc controlee
    aussi bien en v1.1 (filtrage par Statut) qu'en v1.0 (Statut ignore).
    """
    anneau = [
        [850052.0, 6799805.0, 310.0],
        [850053.0, 6799806.0, 311.0],
        [850054.0, 6799805.0, 310.5],
        [850055.0, 6799804.0, 310.2],
        [850052.0, 6799805.0, 310.0],
    ]
    features = [
        construire_feature_avec_proprietes("geom-1", "MultiPolygon", [[anneau]], {CHAMP_STATUT: VALEUR_STATUT_V1_1})
    ]
    ecrire_collection(str(tmp_path / FICHIER_SOURCE), features)
    return str(tmp_path)


class TestCli:
    """Tests d'integration de l'interface CLI avec API mockee."""

    @patch("controle_e203._requeter_api_ign")
    def test_execution_avec_anomalies(self, mock_api: MagicMock, repertoire_test: str) -> None:
        mock_api.return_value = reponse_api_mock([315.0, 311.2, 310.3, 310.0, 315.0])

        resultat = executer_controle_cli(repertoire_test)
        assert resultat["succes"] is True
        assert resultat["nombre_sommets"] == 5
        assert resultat["nombre_anomalies"] >= 1

        chemin_sortie = os.path.join(repertoire_test, FICHIER_SORTIE)
        assert os.path.isfile(chemin_sortie)

        with open(chemin_sortie, encoding="utf-8") as f:
            contenu = json.load(f)
        assert contenu["type"] == "FeatureCollection"
        assert len(contenu["features"]) >= 1

    @patch("controle_e203._requeter_api_ign")
    def test_execution_sans_anomalie(self, mock_api: MagicMock, repertoire_test: str) -> None:
        mock_api.return_value = reponse_api_mock([310.1, 311.1, 310.6, 310.3, 310.1])

        resultat = executer_controle_cli(repertoire_test)
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0

    @patch("controle_e203._requeter_api_ign")
    def test_repertoire_sortie_distinct(self, mock_api: MagicMock, repertoire_test: str, tmp_path: Any) -> None:
        mock_api.return_value = reponse_api_mock([315.0, 311.2, 310.3, 310.0, 315.0])
        dossier_sortie = tmp_path / "sortie"

        resultat = executer_controle_cli(repertoire_test, str(dossier_sortie))
        assert resultat["succes"] is True
        assert os.path.isfile(os.path.join(str(dossier_sortie), FICHIER_SORTIE))

    @patch("controle_e203._requeter_api_ign")
    def test_aucun_fichier_sans_anomalie(self, mock_api: MagicMock, repertoire_test: str) -> None:
        mock_api.return_value = reponse_api_mock([310.1, 311.1, 310.6, 310.3, 310.1])

        resultat = executer_controle_cli(repertoire_test)
        assert resultat["nombre_anomalies"] == 0
        assert resultat["sortie"] is None
        assert not os.path.isfile(os.path.join(repertoire_test, FICHIER_SORTIE))

    def test_fichier_source_absent_retourne_erreur(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False
        assert "erreur" in resultat

    def test_collection_vide_retourne_erreur(self, tmp_path: Any) -> None:
        ecrire_collection(str(tmp_path / FICHIER_SOURCE), [])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False

    @patch("controle_e203._requeter_api_ign")
    def test_api_echoue_produit_collection_vide(self, mock_api: MagicMock, repertoire_test: str) -> None:
        mock_api.return_value = None

        resultat = executer_controle_cli(repertoire_test)
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0


# --------------------------------------------------------------------------- #
# Tests de la gestion des versions RecoStaR
# --------------------------------------------------------------------------- #


# Anneau ferme a 5 sommets reutilise par les tests de version
_ANNEAU_VERSION = [
    [850052.0, 6799805.0, 310.0],
    [850053.0, 6799806.0, 311.0],
    [850054.0, 6799805.0, 310.5],
    [850055.0, 6799804.0, 310.2],
    [850052.0, 6799805.0, 310.0],
]


def _geom_supp_avec_statut(identifiant: str, statut: str | None) -> dict[str, Any]:
    """Construit une geometrie supplementaire MultiPolygon avec un Statut optionnel."""
    proprietes = {CHAMP_STATUT: statut} if statut is not None else {}
    return construire_feature_avec_proprietes(identifiant, "MultiPolygon", [[_ANNEAU_VERSION]], proprietes)


class TestFiltrerFeaturesSelonStatut:
    """Tests du filtrage des entites selon le Statut et la version."""

    def test_v1_1_conserve_under_commissioning(self) -> None:
        features = [_geom_supp_avec_statut("g1", VALEUR_STATUT_V1_1)]
        resultat = filtrer_features_selon_statut(features, "1.1")
        assert len(resultat) == 1

    def test_v1_1_exclut_autre_statut(self) -> None:
        features = [_geom_supp_avec_statut("g1", "Functional")]
        assert filtrer_features_selon_statut(features, "1.1") == []

    def test_v1_1_exclut_statut_absent(self) -> None:
        features = [_geom_supp_avec_statut("g1", None)]
        assert filtrer_features_selon_statut(features, "1.1") == []

    def test_v1_1_filtre_mixte(self) -> None:
        features = [
            _geom_supp_avec_statut("g1", VALEUR_STATUT_V1_1),
            _geom_supp_avec_statut("g2", "Projected"),
            _geom_supp_avec_statut("g3", VALEUR_STATUT_V1_1),
        ]
        resultat = filtrer_features_selon_statut(features, "1.1")
        assert {f["properties"]["id"] for f in resultat} == {"g1", "g3"}

    def test_v1_0_retourne_liste_inchangee(self) -> None:
        # En v1.0, aucun filtrage : la liste d'origine est retournee sans copie.
        features = [_geom_supp_avec_statut("g1", "Functional")]
        assert filtrer_features_selon_statut(features, "1.0") is features

    def test_version_inconnue_retourne_liste_inchangee(self) -> None:
        features = [_geom_supp_avec_statut("g1", None)]
        assert filtrer_features_selon_statut(features, "auto") is features


class TestDeterminerVersionEffective:
    """Tests de la resolution de version (mecanisme E204 reutilise)."""

    def test_version_explicite_prioritaire(self, tmp_path: Any) -> None:
        # Mode explicite : aucune detection, la version demandee est appliquee.
        assert determiner_version_effective(str(tmp_path), "1.0") == "1.0"
        assert determiner_version_effective(str(tmp_path), "1.1") == "1.1"

    def test_auto_detecte_v1_0_via_type_leve(self, tmp_path: Any) -> None:
        point_leve = construire_feature_avec_proprietes("pl1", "Point", [0.0, 0.0], {"TypeLeve": "Z"})
        ecrire_collection(str(tmp_path / FICHIER_DETECTION_VERSION), [point_leve])
        assert determiner_version_effective(str(tmp_path), "auto") == "1.0"

    def test_auto_sans_fichier_detection_repli_defaut(self, tmp_path: Any) -> None:
        # Fichier de detection absent : repli sur la version par defaut (1.1).
        assert determiner_version_effective(str(tmp_path), "auto") == "1.1"

    def test_auto_sans_type_leve_repli_defaut(self, tmp_path: Any) -> None:
        point_leve = construire_feature("pl1", "Point", [0.0, 0.0])
        ecrire_collection(str(tmp_path / FICHIER_DETECTION_VERSION), [point_leve])
        assert determiner_version_effective(str(tmp_path), "auto") == "1.1"


class TestCliVersions:
    """Tests d'integration du comportement d'E203 selon la version RecoStaR."""

    @patch("controle_e203._requeter_api_ign")
    def test_v1_1_controle_uniquement_under_commissioning(self, mock_api: MagicMock, tmp_path: Any) -> None:
        features = [
            _geom_supp_avec_statut("g-uc", VALEUR_STATUT_V1_1),
            _geom_supp_avec_statut("g-func", "Functional"),
        ]
        ecrire_collection(str(tmp_path / FICHIER_SOURCE), features)
        mock_api.return_value = reponse_api_mock([315.0, 311.2, 310.3, 310.0, 315.0])

        resultat = executer_controle_cli(str(tmp_path), version="1.1")
        assert resultat["succes"] is True
        assert resultat["version_detectee"] == "1.1"
        # Seuls les 5 sommets de l'entite UnderCommissionning sont controles
        assert resultat["nombre_sommets"] == 5

    @patch("controle_e203._requeter_api_ign")
    def test_v1_1_sans_entite_eligible_succes_vide(self, mock_api: MagicMock, tmp_path: Any) -> None:
        features = [
            _geom_supp_avec_statut("g1", "Functional"),
            _geom_supp_avec_statut("g2", "Projected"),
        ]
        ecrire_collection(str(tmp_path / FICHIER_SOURCE), features)

        resultat = executer_controle_cli(str(tmp_path), version="1.1")
        assert resultat["succes"] is True
        assert resultat["nombre_sommets"] == 0
        assert resultat["nombre_anomalies"] == 0
        # L'API ne doit pas etre interrogee en l'absence de sommet a controler
        mock_api.assert_not_called()
        assert resultat["sortie"] is None
        assert not os.path.isfile(os.path.join(str(tmp_path), FICHIER_SORTIE))

    @patch("controle_e203._requeter_api_ign")
    def test_v1_0_controle_toutes_entites(self, mock_api: MagicMock, tmp_path: Any) -> None:
        features = [
            _geom_supp_avec_statut("g1", "Functional"),
            _geom_supp_avec_statut("g2", None),
        ]
        ecrire_collection(str(tmp_path / FICHIER_SOURCE), features)
        mock_api.return_value = reponse_api_mock([310.1] * 10)

        resultat = executer_controle_cli(str(tmp_path), version="1.0")
        assert resultat["succes"] is True
        assert resultat["version_detectee"] == "1.0"
        # En v1.0, le Statut est ignore : les 2 entites (5 sommets chacune) sont controlees
        assert resultat["nombre_sommets"] == 10
