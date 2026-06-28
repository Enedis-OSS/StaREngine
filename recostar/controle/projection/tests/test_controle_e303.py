"""
Tests unitaires du controle d'appartenance a l'emprise DR (E303).

Couvre les cas nominaux et les cas limites :
- extraction du prefixe depuis un numero d'affaire (formats RAC et DA)
- construction des index de recherche
- resolution du numero vers les codes repertoire DR
- algorithme Ray Casting (point dans anneau, polygon, emprises)
- calcul de bbox et filtrage spatial
- detection des entites hors emprise
- construction du GeoJSON de sortie
- execution du controle en mode CLI (avec mocks pour les fichiers de reference)
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

from controle_e303 import (
    PRIORITE_ANOMALIE,
    _appliquer_transformation,
    _calculer_bbox,
    _construire_index,
    _creer_transformateur,
    _extraire_nom_crs,
    _extraire_point_representatif,
    _extraire_prefixe,
    _point_dans_anneau,
    _point_dans_emprise,
    construire_geojson_ecarts,
    detecter_entites_hors_emprise,
    executer_controle_cli,
    point_dans_emprises,
    resoudre_repertoires,
)
from utils_tests import construire_feature, ecrire_collection

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _emprise_carre(xmin: float, ymin: float, xmax: float, ymax: float, code: str = "TEST") -> dict[str, Any]:
    """Construit une emprise rectangulaire avec bbox precalculee."""
    anneau = [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax], [xmin, ymin]]
    return {
        "code": code,
        "coordonnees": [anneau],
        "bbox": (xmin, ymin, xmax, ymax),
    }


def _references_test() -> list[dict[str, Any]]:
    """Liste minimale de references DR pour les tests."""
    return [
        {
            "trigramme_racing": "CVL",
            "ref_dossier": "DA28",
            "repertoire": "8A",
        },
        {
            "trigramme_racing": "NOR",
            "ref_dossier": "DB22",
            "repertoire": "2B",
        },
        # Trigramme a plusieurs repertoires (simulant le cas frontiere)
        {
            "trigramme_racing": "FRO",
            "ref_dossier": "DF01",
            "repertoire": "1Z",
        },
        {
            "trigramme_racing": "FRO",
            "ref_dossier": "DF02",
            "repertoire": "2Z",
        },
    ]


# --------------------------------------------------------------------------- #
# Extraction du prefixe
# --------------------------------------------------------------------------- #


class TestExtrairePrefixe:
    """Tests de _extraire_prefixe pour les formats RAC et DA."""

    def test_format_rac_retourne_trigramme(self) -> None:
        prefixe, champ, erreur = _extraire_prefixe("RAC-CVL-25-007998")
        assert prefixe == "CVL"
        assert champ == "trigramme_racing"
        assert erreur is None

    def test_format_rac_normalise_majuscule(self) -> None:
        prefixe, _, _ = _extraire_prefixe("rac-cvl-25-007998")
        assert prefixe == "CVL"

    def test_format_rac_sans_trigramme_retourne_erreur(self) -> None:
        _, _, erreur = _extraire_prefixe("RAC--25-007998")
        assert erreur is not None

    def test_format_da_retourne_ref_dossier(self) -> None:
        prefixe, champ, erreur = _extraire_prefixe("DA21/256553")
        assert prefixe == "DA21"
        assert champ == "ref_dossier"
        assert erreur is None

    def test_format_da_normalise_majuscule(self) -> None:
        prefixe, _, _ = _extraire_prefixe("da21/256553")
        assert prefixe == "DA21"

    def test_format_da_vide_avant_slash_retourne_erreur(self) -> None:
        _, _, erreur = _extraire_prefixe("/256553")
        assert erreur is not None

    def test_format_inconnu_retourne_erreur(self) -> None:
        _, _, erreur = _extraire_prefixe("INCONNU123")
        assert erreur is not None

    def test_format_vide_retourne_erreur(self) -> None:
        _, _, erreur = _extraire_prefixe("")
        assert erreur is not None

    def test_espaces_en_debut_fin_ignores(self) -> None:
        prefixe, _, erreur = _extraire_prefixe("  RAC-NOR-25-001234  ")
        assert erreur is None
        assert prefixe == "NOR"


# --------------------------------------------------------------------------- #
# Construction des index
# --------------------------------------------------------------------------- #


class TestConstruireIndex:
    """Tests de _construire_index."""

    def test_index_trigramme_simple(self) -> None:
        refs = [{"trigramme_racing": "CVL", "ref_dossier": "DA28", "repertoire": "8A"}]
        index_t, _ = _construire_index(refs)
        assert index_t["CVL"] == {"8A"}

    def test_index_dossier_simple(self) -> None:
        refs = [{"trigramme_racing": "CVL", "ref_dossier": "DA28", "repertoire": "8A"}]
        _, index_d = _construire_index(refs)
        assert index_d["DA28"] == "8A"

    def test_trigramme_multi_repertoires(self) -> None:
        index_t, _ = _construire_index(_references_test())
        assert index_t["FRO"] == {"1Z", "2Z"}

    def test_cles_normalisees_majuscule(self) -> None:
        refs = [{"trigramme_racing": "cvl", "ref_dossier": "da28", "repertoire": "8A"}]
        index_t, index_d = _construire_index(refs)
        assert "CVL" in index_t
        assert "DA28" in index_d

    def test_champs_absents_ignores(self) -> None:
        refs = [{"repertoire": "8A"}]
        index_t, index_d = _construire_index(refs)
        assert index_t == {}
        assert index_d == {}


# --------------------------------------------------------------------------- #
# Resolution du numero d'affaire
# --------------------------------------------------------------------------- #


class TestResoudreRepertoires:
    """Tests de resoudre_repertoires."""

    def _index(self) -> tuple[dict[str, set[str]], dict[str, str]]:
        return _construire_index(_references_test())

    def test_format_rac_resout_repertoire(self) -> None:
        index_t, index_d = self._index()
        repertoires, erreur = resoudre_repertoires("RAC-CVL-25-007998", index_t, index_d)
        assert erreur is None
        assert repertoires == {"8A"}

    def test_format_da_resout_repertoire(self) -> None:
        index_t, index_d = self._index()
        repertoires, erreur = resoudre_repertoires("DA28/001234", index_t, index_d)
        assert erreur is None
        assert repertoires == {"8A"}

    def test_trigramme_multi_repertoires(self) -> None:
        index_t, index_d = self._index()
        repertoires, erreur = resoudre_repertoires("RAC-FRO-25-001234", index_t, index_d)
        assert erreur is None
        assert repertoires == {"1Z", "2Z"}

    def test_trigramme_inconnu_retourne_erreur(self) -> None:
        index_t, index_d = self._index()
        repertoires, erreur = resoudre_repertoires("RAC-XYZ-25-001234", index_t, index_d)
        assert repertoires is None
        assert erreur is not None

    def test_ref_dossier_inconnu_retourne_erreur(self) -> None:
        index_t, index_d = self._index()
        repertoires, erreur = resoudre_repertoires("ZZ99/001234", index_t, index_d)
        assert repertoires is None
        assert erreur is not None

    def test_format_invalide_retourne_erreur(self) -> None:
        index_t, index_d = self._index()
        repertoires, erreur = resoudre_repertoires("FORMAT_INCONNU", index_t, index_d)
        assert repertoires is None
        assert erreur is not None


# --------------------------------------------------------------------------- #
# Bounding box
# --------------------------------------------------------------------------- #


class TestCalculerBbox:
    """Tests de _calculer_bbox."""

    def test_carre_simple(self) -> None:
        anneau = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0], [0.0, 0.0]]
        assert _calculer_bbox(anneau) == (0.0, 0.0, 10.0, 10.0)

    def test_coordonnees_negatives(self) -> None:
        anneau = [[-5.0, -3.0], [2.0, -3.0], [2.0, 4.0], [-5.0, 4.0], [-5.0, -3.0]]
        xmin, ymin, xmax, ymax = _calculer_bbox(anneau)
        assert xmin == -5.0 and ymin == -3.0
        assert xmax == 2.0 and ymax == 4.0


# --------------------------------------------------------------------------- #
# Ray Casting — point dans anneau
# --------------------------------------------------------------------------- #


class TestPointDansAnneau:
    """Tests de _point_dans_anneau."""

    def _carre(self) -> list[list[float]]:
        return [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0], [0.0, 0.0]]

    def test_point_interieur(self) -> None:
        assert _point_dans_anneau(5.0, 5.0, self._carre()) is True

    def test_point_exterieur(self) -> None:
        assert _point_dans_anneau(15.0, 5.0, self._carre()) is False

    def test_point_tres_eloigne(self) -> None:
        assert _point_dans_anneau(1000.0, 1000.0, self._carre()) is False

    def test_anneau_vide_retourne_false(self) -> None:
        assert _point_dans_anneau(5.0, 5.0, []) is False

    def test_coin_superieur_droit(self) -> None:
        assert _point_dans_anneau(9.9, 9.9, self._carre()) is True


# --------------------------------------------------------------------------- #
# Point dans emprise (avec bbox)
# --------------------------------------------------------------------------- #


class TestPointDansEmprise:
    """Tests de _point_dans_emprise et point_dans_emprises."""

    def test_point_interieur_dans_emprise(self) -> None:
        emprise = _emprise_carre(0, 0, 100, 100)
        assert _point_dans_emprise(50.0, 50.0, emprise) is True

    def test_point_exterieur_hors_emprise(self) -> None:
        emprise = _emprise_carre(0, 0, 100, 100)
        assert _point_dans_emprise(200.0, 200.0, emprise) is False

    def test_point_hors_bbox_rejete_sans_polygon(self) -> None:
        # Hors bbox -> rejete immediatement sans calcul Ray Casting
        emprise = _emprise_carre(0, 0, 100, 100)
        assert _point_dans_emprise(-1.0, 50.0, emprise) is False

    def test_point_dans_une_des_emprises(self) -> None:
        emprises = [
            _emprise_carre(0, 0, 100, 100, "DR1"),
            _emprise_carre(200, 200, 300, 300, "DR2"),
        ]
        assert point_dans_emprises(50.0, 50.0, emprises) is True

    def test_point_hors_de_toutes_emprises(self) -> None:
        emprises = [
            _emprise_carre(0, 0, 100, 100, "DR1"),
            _emprise_carre(200, 200, 300, 300, "DR2"),
        ]
        assert point_dans_emprises(150.0, 150.0, emprises) is False

    def test_point_dans_seconde_emprise_uniquement(self) -> None:
        emprises = [
            _emprise_carre(0, 0, 100, 100, "DR1"),
            _emprise_carre(200, 200, 300, 300, "DR2"),
        ]
        assert point_dans_emprises(250.0, 250.0, emprises) is True


# --------------------------------------------------------------------------- #
# Extraction du CRS et transformateur
# --------------------------------------------------------------------------- #


class TestExtraireNomCrs:
    """Tests de _extraire_nom_crs."""

    def test_crs_present_retourne_nom(self) -> None:
        collection = {
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:EPSG::3947"},
            }
        }
        assert _extraire_nom_crs(collection) == "urn:ogc:def:crs:EPSG::3947"

    def test_crs_absent_retourne_none(self) -> None:
        assert _extraire_nom_crs({"type": "FeatureCollection"}) is None

    def test_nom_vide_retourne_none(self) -> None:
        collection = {"crs": {"type": "name", "properties": {"name": ""}}}
        assert _extraire_nom_crs(collection) is None


class TestCreerTransformateur:
    """Tests de _creer_transformateur."""

    def test_crs_identique_retourne_none(self) -> None:
        assert _creer_transformateur("EPSG:2154") is None

    def test_crs_different_retourne_transformer(self) -> None:
        t = _creer_transformateur("urn:ogc:def:crs:EPSG::3947")
        assert t is not None

    def test_crs_invalide_retourne_none(self) -> None:
        assert _creer_transformateur("CRS_INVALIDE_XYZ") is None

    def test_crs_none_retourne_none(self) -> None:
        assert _creer_transformateur(None) is None


class TestAppliquerTransformation:
    """Tests de _appliquer_transformation."""

    def test_sans_transformateur_coordonnees_inchangees(self) -> None:
        assert _appliquer_transformation(100.0, 200.0, None) == (100.0, 200.0)

    def test_avec_transformateur_coordonnees_transformees(self) -> None:
        t = _creer_transformateur("urn:ogc:def:crs:EPSG::3947")
        assert t is not None
        x, y = _appliquer_transformation(1030000.0, 6270000.0, t)
        # Le point doit etre transforme (coordonnees differentes)
        assert x != 1030000.0 or y != 6270000.0


# --------------------------------------------------------------------------- #
# Extraction du point representatif
# --------------------------------------------------------------------------- #


class TestExtrairePointRepresentatif:
    """Tests de _extraire_point_representatif."""

    def test_point_retourne_coordonnees(self) -> None:
        geom = {"type": "Point", "coordinates": [5.0, 10.0]}
        pt = _extraire_point_representatif(geom)
        assert pt == (5.0, 10.0)

    def test_linestring_retourne_centroide(self) -> None:
        geom = {"type": "LineString", "coordinates": [[0.0, 0.0], [4.0, 2.0]]}
        pt = _extraire_point_representatif(geom)
        assert pt is not None
        assert pt == (2.0, 1.0)

    def test_type_inconnu_retourne_none(self) -> None:
        geom = {"type": "GeometryCollection"}
        assert _extraire_point_representatif(geom) is None

    def test_coordonnees_absentes_retourne_none(self) -> None:
        assert _extraire_point_representatif({"type": "Point"}) is None


# --------------------------------------------------------------------------- #
# Detection des entites hors emprise
# --------------------------------------------------------------------------- #


class TestDetecterEntitesHorsEmprise:
    """Tests de detecter_entites_hors_emprise."""

    def _emprises(self) -> list[dict[str, Any]]:
        return [_emprise_carre(0, 0, 1000, 1000)]

    def test_entite_dans_emprise_non_signalee(self) -> None:
        features = [construire_feature("e1", "Point", [500.0, 500.0])]
        anomalies, _ = detecter_entites_hors_emprise(features, "f.geojson", self._emprises(), None)
        assert anomalies == []

    def test_entite_hors_emprise_signalee(self) -> None:
        features = [construire_feature("e1", "Point", [9999.0, 9999.0])]
        anomalies, _ = detecter_entites_hors_emprise(features, "f.geojson", self._emprises(), None)
        assert len(anomalies) == 1
        assert anomalies[0]["id_entite"] == "e1"

    def test_feature_sans_geometrie_ignoree(self) -> None:
        features = [{"type": "Feature", "properties": {}, "geometry": None}]
        anomalies, nb = detecter_entites_hors_emprise(features, "f.geojson", self._emprises(), None)
        assert anomalies == []
        assert nb == 0

    def test_nb_entites_analysees_correct(self) -> None:
        features = [
            construire_feature("e1", "Point", [500.0, 500.0]),  # dans emprise
            construire_feature("e2", "Point", [9999.0, 9999.0]),  # hors emprise
            {"type": "Feature", "properties": {}, "geometry": None},  # ignoree
        ]
        anomalies, nb = detecter_entites_hors_emprise(features, "f.geojson", self._emprises(), None)
        assert len(anomalies) == 1
        assert nb == 2

    def test_fichier_source_copie(self) -> None:
        features = [construire_feature("e1", "Point", [9999.0, 9999.0])]
        anomalies, _ = detecter_entites_hors_emprise(features, "ma_couche.geojson", self._emprises(), None)
        assert anomalies[0]["fichier_source"] == "ma_couche.geojson"


# --------------------------------------------------------------------------- #
# Construction du GeoJSON de sortie
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    def _anomalie(self) -> dict[str, Any]:
        return {
            "fichier_source": "f.geojson",
            "id_entite": "e1",
            "type_geometrie": "Point",
            "geometrie": {"type": "Point", "coordinates": [9999.0, 9999.0]},
        }

    def test_type_feature_collection(self) -> None:
        assert construire_geojson_ecarts([self._anomalie()], "8A")["type"] == "FeatureCollection"

    def test_properties_obligatoires(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()], "8A")["features"][0]["properties"]
        assert props["codes_dr_autorises"] == "8A"
        assert props["type_anomalie"] == "hors_emprise_dr"
        assert props["priorite"] == PRIORITE_ANOMALIE

    def test_geometrie_originale_conservee(self) -> None:
        geom = construire_geojson_ecarts([self._anomalie()], "8A")["features"][0]["geometry"]
        assert geom["type"] == "Point"

    def test_sans_crs_pas_de_champ_crs(self) -> None:
        assert "crs" not in construire_geojson_ecarts([self._anomalie()], "8A")

    def test_avec_crs_champ_present(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        resultat = construire_geojson_ecarts([self._anomalie()], "8A", crs=crs)
        assert resultat["crs"] == crs

    def test_liste_vide_aucun_feature(self) -> None:
        assert construire_geojson_ecarts([], "8A")["features"] == []


# --------------------------------------------------------------------------- #
# Tests d'integration du controle CLI
# --------------------------------------------------------------------------- #

_REFS_MOCK = [{"trigramme_racing": "CVL", "ref_dossier": "DA28", "repertoire": "8A"}]
_EMPRISE_8A = [_emprise_carre(0, 0, 1_000_000, 1_000_000, "8A")]


class TestCli:
    """Tests de executer_controle_cli (avec mocks des fichiers de reference)."""

    def test_numero_affaire_absent_retourne_erreur(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path), None)
        assert resultat["succes"] is False
        assert "numero_affaire" in resultat["erreur"]

    def test_numero_affaire_vide_retourne_erreur(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path), "")
        assert resultat["succes"] is False

    def test_repertoire_inexistant_retourne_erreur(self) -> None:
        resultat = executer_controle_cli("/chemin/inexistant", "RAC-CVL-25-007998")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    @patch("controle_e303._charger_references")
    def test_format_affaire_invalide_retourne_erreur(self, mock_refs: Any, tmp_path: Any) -> None:
        mock_refs.return_value = (_REFS_MOCK, None)
        resultat = executer_controle_cli(str(tmp_path), "FORMAT_INVALIDE")
        assert resultat["succes"] is False

    @patch("controle_e303._charger_references")
    def test_trigramme_inconnu_retourne_erreur(self, mock_refs: Any, tmp_path: Any) -> None:
        mock_refs.return_value = (_REFS_MOCK, None)
        resultat = executer_controle_cli(str(tmp_path), "RAC-XYZ-25-001234")
        assert resultat["succes"] is False
        assert "XYZ" in resultat["erreur"]

    @patch("controle_e303._charger_emprises_dr")
    @patch("controle_e303._charger_references")
    def test_sans_geojson_retourne_erreur(self, mock_refs: Any, mock_emprises: Any, tmp_path: Any) -> None:
        mock_refs.return_value = (_REFS_MOCK, None)
        mock_emprises.return_value = (_EMPRISE_8A, None)
        resultat = executer_controle_cli(str(tmp_path), "RAC-CVL-25-007998")
        assert resultat["succes"] is False
        assert "GeoJSON" in resultat["erreur"]

    @patch("controle_e303._charger_emprises_dr")
    @patch("controle_e303._charger_references")
    def test_nominal_sans_anomalie(self, mock_refs: Any, mock_emprises: Any, tmp_path: Any) -> None:
        mock_refs.return_value = (_REFS_MOCK, None)
        mock_emprises.return_value = (_EMPRISE_8A, None)
        features = [construire_feature("e1", "Point", [500000.0, 500000.0])]
        ecrire_collection(str(tmp_path / "couche.geojson"), features)
        resultat = executer_controle_cli(str(tmp_path), "RAC-CVL-25-007998")
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["codes_dr"] == "8A"

    @patch("controle_e303._charger_emprises_dr")
    @patch("controle_e303._charger_references")
    def test_nominal_avec_anomalie(self, mock_refs: Any, mock_emprises: Any, tmp_path: Any) -> None:
        mock_refs.return_value = (_REFS_MOCK, None)
        mock_emprises.return_value = (_EMPRISE_8A, None)
        # Point hors de l'emprise [0, 1_000_000]²
        features = [construire_feature("e1", "Point", [2_000_000.0, 2_000_000.0])]
        ecrire_collection(str(tmp_path / "couche.geojson"), features)
        resultat = executer_controle_cli(str(tmp_path), "RAC-CVL-25-007998")
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 1

    @patch("controle_e303._charger_emprises_dr")
    @patch("controle_e303._charger_references")
    def test_fichier_ecarts_cree(self, mock_refs: Any, mock_emprises: Any, tmp_path: Any) -> None:
        mock_refs.return_value = (_REFS_MOCK, None)
        mock_emprises.return_value = (_EMPRISE_8A, None)
        ecrire_collection(
            str(tmp_path / "couche.geojson"),
            [construire_feature("e1", "Point", [500000.0, 500000.0])],
        )
        executer_controle_cli(str(tmp_path), "RAC-CVL-25-007998")
        assert os.path.isfile(str(tmp_path / "ecarts_emprise_dr.geojson"))

    @patch("controle_e303._charger_emprises_dr")
    @patch("controle_e303._charger_references")
    def test_rapport_contient_champs_obligatoires(self, mock_refs: Any, mock_emprises: Any, tmp_path: Any) -> None:
        mock_refs.return_value = (_REFS_MOCK, None)
        mock_emprises.return_value = (_EMPRISE_8A, None)
        ecrire_collection(
            str(tmp_path / "couche.geojson"),
            [construire_feature("e1", "Point", [500000.0, 500000.0])],
        )
        resultat = executer_controle_cli(str(tmp_path), "RAC-CVL-25-007998")
        for champ in (
            "succes",
            "priorite",
            "nombre_anomalies",
            "entites_analysees",
            "fichiers_analyses",
            "numero_affaire",
            "codes_dr",
            "sortie",
        ):
            assert champ in resultat, f"Champ manquant : {champ}"

    @patch("controle_e303._charger_emprises_dr")
    @patch("controle_e303._charger_references")
    def test_format_da_accepte(self, mock_refs: Any, mock_emprises: Any, tmp_path: Any) -> None:
        mock_refs.return_value = (_REFS_MOCK, None)
        mock_emprises.return_value = (_EMPRISE_8A, None)
        ecrire_collection(
            str(tmp_path / "couche.geojson"),
            [construire_feature("e1", "Point", [500000.0, 500000.0])],
        )
        resultat = executer_controle_cli(str(tmp_path), "DA28/001234")
        assert resultat["succes"] is True
        assert resultat["codes_dr"] == "8A"

    @patch("controle_e303._charger_emprises_dr")
    @patch("controle_e303._charger_references")
    def test_dossier_sortie_distinct(self, mock_refs: Any, mock_emprises: Any, tmp_path: Any) -> None:
        mock_refs.return_value = (_REFS_MOCK, None)
        mock_emprises.return_value = (_EMPRISE_8A, None)
        ecrire_collection(
            str(tmp_path / "couche.geojson"),
            [construire_feature("e1", "Point", [500000.0, 500000.0])],
        )
        dossier_sortie = str(tmp_path / "sortie")
        executer_controle_cli(str(tmp_path), "RAC-CVL-25-007998", dossier_sortie)
        assert os.path.isfile(os.path.join(dossier_sortie, "ecarts_emprise_dr.geojson"))

    @patch("controle_e303._charger_emprises_dr")
    @patch("controle_e303._charger_references")
    def test_numero_affaire_restitue_dans_rapport(self, mock_refs: Any, mock_emprises: Any, tmp_path: Any) -> None:
        mock_refs.return_value = (_REFS_MOCK, None)
        mock_emprises.return_value = (_EMPRISE_8A, None)
        ecrire_collection(
            str(tmp_path / "couche.geojson"),
            [construire_feature("e1", "Point", [500000.0, 500000.0])],
        )
        resultat = executer_controle_cli(str(tmp_path), "RAC-CVL-25-007998")
        assert resultat["numero_affaire"] == "RAC-CVL-25-007998"
