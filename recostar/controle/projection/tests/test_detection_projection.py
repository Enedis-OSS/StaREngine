"""
Tests du moteur de projection et des trois controles qu'il sert.

Couvre les cas nominaux et les cas limites :
- normalisation des codes EPSG (formats URN et direct)
- lecture du SRS depuis _metadata.json
- extraction du CRS depuis une FeatureCollection
- detection des entites en ecart de projection
- construction du GeoJSON de sortie
- execution CLI bout en bout via tmp_path
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from recostar.controle.fonctions_communes.geojson import PRIORITE_FORTE
from recostar.controle.projection.detection_projection import (
    TYPE_DIFFERENTE,
    _construire_crs_depuis_epsg,
    construire_geojson_ecarts,
    detecter_ecart_au_srs,
    extraire_epsg_collection,
    lire_srs_attendu,
    normaliser_epsg,
)
from recostar.controle.projection.e5105 import FICHIER_SORTIE, executer_controle_cli
from recostar.controle.projection.e5105 import PROFIL_ECARTS as PROFIL_ECARTS_5105
from recostar.controle.projection.tests.utils_tests import (
    construire_feature,
    ecrire_collection,
    ecrire_collection_avec_crs,
    ecrire_metadata,
)

# --------------------------------------------------------------------------- #
# Tests de la normalisation EPSG
# --------------------------------------------------------------------------- #


class TestNormaliserEpsg:
    """Tests de la normalisation des identifiants de projection."""

    def test_urn_double_deux_points(self) -> None:
        assert normaliser_epsg("urn:ogc:def:crs:EPSG::3947") == "EPSG:3947"

    def test_urn_avec_version(self) -> None:
        assert normaliser_epsg("urn:ogc:def:crs:EPSG:6.18.3:2154") == "EPSG:2154"

    def test_format_epsg_majuscule(self) -> None:
        assert normaliser_epsg("EPSG:4326") == "EPSG:4326"

    def test_format_epsg_minuscule(self) -> None:
        assert normaliser_epsg("epsg:2154") == "EPSG:2154"

    def test_format_epsg_casse_mixte(self) -> None:
        assert normaliser_epsg("Epsg:3947") == "EPSG:3947"

    def test_espaces_en_debut_fin(self) -> None:
        assert normaliser_epsg("  EPSG:3947  ") == "EPSG:3947"

    def test_format_inconnu_retourne_none(self) -> None:
        assert normaliser_epsg("WGS84") is None

    def test_code_non_numerique_retourne_none(self) -> None:
        assert normaliser_epsg("EPSG:ABC") is None

    def test_urn_code_non_numerique_retourne_none(self) -> None:
        assert normaliser_epsg("urn:ogc:def:crs:EPSG::ABCD") is None

    def test_chaine_vide_retourne_none(self) -> None:
        assert normaliser_epsg("") is None


# --------------------------------------------------------------------------- #
# Tests de la lecture du SRS attendu
# --------------------------------------------------------------------------- #


class TestLireSrsAttendu:
    """Tests de la lecture du SRS depuis _metadata.json."""

    def test_srs_valide_retourne_epsg(self, tmp_path: Any) -> None:
        ecrire_metadata(str(tmp_path / "_metadata.json"), "EPSG:3947")
        epsg, erreur = lire_srs_attendu(str(tmp_path))
        assert epsg == "EPSG:3947"
        assert erreur is None

    def test_srs_urn_valide(self, tmp_path: Any) -> None:
        ecrire_metadata(str(tmp_path / "_metadata.json"), "urn:ogc:def:crs:EPSG::2154")
        epsg, erreur = lire_srs_attendu(str(tmp_path))
        assert epsg == "EPSG:2154"
        assert erreur is None

    def test_fichier_absent_sans_objet(self, tmp_path: Any) -> None:
        epsg, erreur = lire_srs_attendu(str(tmp_path))
        assert epsg is None
        assert erreur is not None

    def test_json_invalide_sans_objet(self, tmp_path: Any) -> None:
        (tmp_path / "_metadata.json").write_text("non-json{", encoding="utf-8")
        epsg, erreur = lire_srs_attendu(str(tmp_path))
        assert epsg is None
        assert erreur is not None

    def test_champ_srs_absent_sans_objet(self, tmp_path: Any) -> None:
        (tmp_path / "_metadata.json").write_text(json.dumps({"Metadata": {}}), encoding="utf-8")
        epsg, erreur = lire_srs_attendu(str(tmp_path))
        assert epsg is None
        assert erreur is not None

    def test_metadata_absent_sans_objet(self, tmp_path: Any) -> None:
        (tmp_path / "_metadata.json").write_text(json.dumps({}), encoding="utf-8")
        epsg, erreur = lire_srs_attendu(str(tmp_path))
        assert epsg is None
        assert erreur is not None

    def test_srs_non_reconnu_sans_objet(self, tmp_path: Any) -> None:
        ecrire_metadata(str(tmp_path / "_metadata.json"), "FORMAT_INCONNU")
        epsg, erreur = lire_srs_attendu(str(tmp_path))
        assert epsg is None
        assert erreur is not None


# --------------------------------------------------------------------------- #
# Tests de l'extraction du CRS depuis une collection
# --------------------------------------------------------------------------- #


class TestExtraireEpsgCollection:
    """Tests de l'extraction du code EPSG depuis une FeatureCollection."""

    def test_crs_urn_extrait_correctement(self) -> None:
        collection = {
            "type": "FeatureCollection",
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:EPSG::3947"},
            },
            "features": [],
        }
        assert extraire_epsg_collection(collection) == "EPSG:3947"

    def test_crs_absent_retourne_none(self) -> None:
        collection = {"type": "FeatureCollection", "features": []}
        assert extraire_epsg_collection(collection) is None

    def test_crs_sans_properties_retourne_none(self) -> None:
        collection = {
            "type": "FeatureCollection",
            "crs": {"type": "name"},
            "features": [],
        }
        assert extraire_epsg_collection(collection) is None

    def test_crs_name_vide_retourne_none(self) -> None:
        collection = {
            "type": "FeatureCollection",
            "crs": {"type": "name", "properties": {"name": ""}},
            "features": [],
        }
        assert extraire_epsg_collection(collection) is None


# --------------------------------------------------------------------------- #
# Tests de la detection des entites en ecart
# --------------------------------------------------------------------------- #


class TestDetecterEntitesProjectionIncorrecte:
    """Tests de la detection des anomalies de projection."""

    def test_projection_correcte_aucune_anomalie(self) -> None:
        features = [construire_feature("e1", "Point", [1.0, 2.0, 3.0])]
        anomalies = detecter_ecart_au_srs(features, "test.geojson", "EPSG:3947", "EPSG:3947")
        assert anomalies == []

    def test_projection_incorrecte_toutes_entites_signalees(self) -> None:
        features = [
            construire_feature("e1", "Point", [1.0, 2.0]),
            construire_feature("e2", "LineString", [[0, 0], [1, 1]]),
        ]
        anomalies = detecter_ecart_au_srs(features, "test.geojson", "EPSG:3947", "EPSG:2154")
        assert len(anomalies) == 2

    def test_projection_absente_toutes_entites_signalees(self) -> None:
        features = [construire_feature("e1", "Point", [1.0, 2.0])]
        anomalies = detecter_ecart_au_srs(features, "test.geojson", "EPSG:3947", None)
        assert len(anomalies) == 1
        assert anomalies[0]["projection_detectee"] == "inconnue"

    def test_entite_sans_geometrie_ignoree(self) -> None:
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {"id": "e1"},
            "geometry": None,
        }
        anomalies = detecter_ecart_au_srs([feature], "test.geojson", "EPSG:3947", "EPSG:2154")
        assert anomalies == []

    def test_proprietes_anomalie_correctes(self) -> None:
        features = [construire_feature("e1", "Point", [1.0, 2.0])]
        anomalies = detecter_ecart_au_srs(features, "mon_fichier.geojson", "EPSG:3947", "EPSG:2154")
        a = anomalies[0]
        assert a["fichier_source"] == "mon_fichier.geojson"
        assert a["id_entite"] == "e1"
        assert a["type_geometrie"] == "Point"
        assert a["projection_attendue"] == "EPSG:3947"
        assert a["projection_detectee"] == "EPSG:2154"

    def test_collection_vide_retourne_liste_vide(self) -> None:
        anomalies = detecter_ecart_au_srs([], "test.geojson", "EPSG:3947", "EPSG:2154")
        assert anomalies == []


# --------------------------------------------------------------------------- #
# Tests du GeoJSON de sortie
# --------------------------------------------------------------------------- #


class TestGeojsonSortie:
    """Tests de la serialisation des anomalies en FeatureCollection."""

    def test_structure_geojson_conforme(self) -> None:
        anomalies = [
            {
                "type_anomalie": TYPE_DIFFERENTE,
                "fichier_source": "test.geojson",
                "id_entite": "e1",
                "type_geometrie": "Point",
                "geometrie": {"type": "Point", "coordinates": [1.0, 2.0]},
                "projection_attendue": "EPSG:3947",
                "projection_detectee": "EPSG:2154",
            }
        ]
        geojson = construire_geojson_ecarts(anomalies, PROFIL_ECARTS_5105)
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 1

        feature = geojson["features"][0]
        props = feature["properties"]
        assert props["fichier_source"] == "test.geojson"
        assert props["id_entite"] == "e1"
        assert props["type_geometrie"] == "Point"
        assert props["projection_attendue"] == "EPSG:3947"
        assert props["projection_detectee"] == "EPSG:2154"
        assert props["type_anomalie"] == TYPE_DIFFERENTE
        assert props["code_controle"] == "E-5105"
        assert props["code_erreur"] == "E-5105"

    def test_geometrie_originale_conservee(self) -> None:
        geom = {"type": "Point", "coordinates": [1.0, 2.0, 3.0]}
        anomalies = [
            {
                "type_anomalie": TYPE_DIFFERENTE,
                "fichier_source": "f.geojson",
                "id_entite": "e1",
                "type_geometrie": "Point",
                "geometrie": geom,
                "projection_attendue": "EPSG:3947",
                "projection_detectee": "EPSG:2154",
            }
        ]
        geojson = construire_geojson_ecarts(anomalies, PROFIL_ECARTS_5105)
        assert geojson["features"][0]["geometry"] == geom

    def test_feature_collection_vide(self) -> None:
        geojson = construire_geojson_ecarts([], PROFIL_ECARTS_5105)
        assert geojson == {"type": "FeatureCollection", "features": []}

    def test_crs_propage_si_present(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::3947"}}
        geojson = construire_geojson_ecarts([], PROFIL_ECARTS_5105, crs)
        assert geojson["crs"] == crs

    def test_crs_absent_si_non_fourni(self) -> None:
        geojson = construire_geojson_ecarts([], PROFIL_ECARTS_5105)
        assert "crs" not in geojson


# --------------------------------------------------------------------------- #
# Tests de la construction du CRS de sortie
# --------------------------------------------------------------------------- #


class TestConstruireCrsDepuisEpsg:
    """Tests de la construction de l'objet CRS GeoJSON."""

    def test_format_urn_genere(self) -> None:
        crs = _construire_crs_depuis_epsg("EPSG:3947")
        assert crs["type"] == "name"
        assert crs["properties"]["name"] == "urn:ogc:def:crs:EPSG::3947"

    def test_code_preserve(self) -> None:
        crs = _construire_crs_depuis_epsg("EPSG:2154")
        assert "2154" in crs["properties"]["name"]


# --------------------------------------------------------------------------- #
# Tests CLI bout en bout
# --------------------------------------------------------------------------- #


@pytest.fixture
def repertoire_conforme(tmp_path: Any) -> str:
    """Repertoire avec metadata et GeoJSON dans la bonne projection."""
    ecrire_metadata(str(tmp_path / "_metadata.json"), "EPSG:3947")
    features = [
        construire_feature("e1", "Point", [1530000.0, 6238000.0, 91.5]),
        construire_feature("e2", "LineString", [[0, 0, 1], [1, 1, 2]]),
    ]
    ecrire_collection_avec_crs(str(tmp_path / "couche_a.geojson"), features, "EPSG:3947")
    return str(tmp_path)


@pytest.fixture
def repertoire_non_conforme(tmp_path: Any) -> str:
    """Repertoire avec un fichier dans une mauvaise projection."""
    ecrire_metadata(str(tmp_path / "_metadata.json"), "EPSG:3947")

    features_ok = [construire_feature("e1", "Point", [1530000.0, 6238000.0, 91.5])]
    ecrire_collection_avec_crs(str(tmp_path / "couche_ok.geojson"), features_ok, "EPSG:3947")

    features_ko = [
        construire_feature("e2", "Point", [700000.0, 6600000.0, 50.0]),
        construire_feature("e3", "LineString", [[0, 0], [1, 1]]),
    ]
    ecrire_collection_avec_crs(str(tmp_path / "couche_ko.geojson"), features_ko, "EPSG:2154")
    return str(tmp_path)


class TestCli:
    """Tests d'integration de l'interface CLI."""

    def test_execution_sans_anomalie(self, repertoire_conforme: str) -> None:
        resultat = executer_controle_cli(repertoire_conforme)
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["fichiers_analyses"] == 1
        assert resultat["projection_attendue"] == "EPSG:3947"

    def test_aucun_fichier_sans_anomalie(self, repertoire_conforme: str) -> None:
        resultat = executer_controle_cli(repertoire_conforme)
        assert resultat["sortie"] is None
        assert not os.path.isfile(os.path.join(repertoire_conforme, FICHIER_SORTIE))

    def test_ecrit_fichier_sortie(self, repertoire_non_conforme: str) -> None:
        resultat = executer_controle_cli(repertoire_non_conforme)
        assert os.path.isfile(resultat["sortie"])
        with open(resultat["sortie"], encoding="utf-8") as fichier:
            contenu = json.load(fichier)
        assert contenu["type"] == "FeatureCollection"
        assert len(contenu["features"]) == 2

    def test_fichier_mauvaise_projection_signale(self, repertoire_non_conforme: str) -> None:
        resultat = executer_controle_cli(repertoire_non_conforme)
        assert resultat["succes"] is True
        # 2 entites de couche_ko signalees, 1 entite de couche_ok conforme
        assert resultat["nombre_anomalies"] == 2
        assert resultat["fichiers_analyses"] == 2

    def test_contenu_geojson_anomalies(self, repertoire_non_conforme: str) -> None:
        resultat = executer_controle_cli(repertoire_non_conforme)
        with open(resultat["sortie"], encoding="utf-8") as fichier:
            contenu = json.load(fichier)
        assert len(contenu["features"]) == 2
        props = contenu["features"][0]["properties"]
        assert props["projection_attendue"] == "EPSG:3947"
        assert props["projection_detectee"] == "EPSG:2154"
        assert props["type_anomalie"] == TYPE_DIFFERENTE
        assert props["code_erreur"] == "E-5105"
        assert props["priorite"] == PRIORITE_FORTE

    def test_crs_sortie_correspond_projection_attendue(self, repertoire_non_conforme: str) -> None:
        resultat = executer_controle_cli(repertoire_non_conforme)
        with open(resultat["sortie"], encoding="utf-8") as fichier:
            contenu = json.load(fichier)
        assert "crs" in contenu
        assert "3947" in contenu["crs"]["properties"]["name"]

    def test_repertoire_sortie_distinct(self, repertoire_non_conforme: str, tmp_path: Any) -> None:
        dossier_sortie = str(tmp_path / "sortie")
        resultat = executer_controle_cli(repertoire_non_conforme, dossier_sortie)
        assert resultat["succes"] is True
        assert os.path.isfile(os.path.join(dossier_sortie, FICHIER_SORTIE))

    def test_repertoire_inexistant_sans_objet(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path / "inexistant"))
        assert resultat["succes"] is False
        assert "erreur" in resultat

    def test_metadata_absent_sans_objet(self, tmp_path: Any) -> None:
        ecrire_collection_avec_crs(
            str(tmp_path / "couche.geojson"),
            [construire_feature("e1", "Point", [0.0, 0.0])],
            "EPSG:3947",
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False
        assert "erreur" in resultat

    def test_aucun_geojson_sans_objet(self, tmp_path: Any) -> None:
        ecrire_metadata(str(tmp_path / "_metadata.json"), "EPSG:3947")
        (tmp_path / "readme.txt").write_text("texte", encoding="utf-8")
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True

    def test_fichier_sans_crs_signale(self, tmp_path: Any) -> None:
        """Un GeoJSON sans champ crs est traite comme projection inconnue."""
        ecrire_metadata(str(tmp_path / "_metadata.json"), "EPSG:3947")
        features = [construire_feature("e1", "Point", [0.0, 0.0])]
        ecrire_collection(str(tmp_path / "sans_crs.geojson"), features)
        # Un crs absent est une declaration manquante : E-2200, non E-5105, qui
        # ne juge que les projections effectivement declarees.
        from recostar.controle.projection.e2200 import executer_controle_cli as executer_2200

        assert executer_controle_cli(str(tmp_path))["nombre_anomalies"] == 0
        resultat = executer_2200(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 1
        with open(resultat["sortie"], encoding="utf-8") as fichier:
            contenu = json.load(fichier)
        props = contenu["features"][0]["properties"]
        assert props["projection_detectee"] == "inconnue"
        assert props["code_erreur"] == "E-2200"

    def test_ecarts_precedents_exclus_de_lanalyse(self, tmp_path: Any) -> None:
        """Les fichiers prefixes 'ecarts_' sont ignores."""
        ecrire_metadata(str(tmp_path / "_metadata.json"), "EPSG:3947")
        features = [construire_feature("e1", "Point", [0.0, 0.0])]
        ecrire_collection_avec_crs(str(tmp_path / "ecarts_precedents.geojson"), features, "EPSG:9999")
        ecrire_collection_avec_crs(str(tmp_path / "couche.geojson"), features, "EPSG:3947")
        resultat = executer_controle_cli(str(tmp_path))
        # Seul couche.geojson est analyse (conforme), ecarts_precedents.geojson exclu
        assert resultat["nombre_anomalies"] == 0
        assert resultat["fichiers_analyses"] == 1

    def test_priorite_deduite_du_code(self, repertoire_non_conforme: str) -> None:
        """Le controle ne declare plus de priorite : elle vient du niveau d'E-5105."""
        resultat = executer_controle_cli(repertoire_non_conforme)
        assert "priorite" not in resultat
        with open(resultat["sortie"], encoding="utf-8") as fichier:
            props = json.load(fichier)["features"][0]["properties"]
        assert props["priorite"] == PRIORITE_FORTE
