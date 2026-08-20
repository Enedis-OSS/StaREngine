"""
Tests unitaires du controle des superpositions de cheminements (controle_e400).

Couvre les cas nominaux et cas limites :
- creation d'entites depuis des features GeoJSON
- chargement d'une couche depuis fichier
- detection des chevauchements lineaires (vs croisements ponctuels)
- classification totale / partielle
- analyse d'une paire d'entites
- detection globale intra et inter-couches
- construction du GeoJSON de sortie
- execution CLI bout en bout via tmp_path
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
from controle_e400 import (
    FICHIER_SORTIE,
    FICHIERS_CHEMINEMENT,
    PRIORITE_ANOMALIE,
    EntiteCheminement,
    _analyser_paire,
    _classifier_superposition,
    _creer_entite_depuis_feature,
    _est_chevauchement_lineaire,
    charger_entites_couche,
    construire_geojson_ecarts,
    detecter_toutes_superpositions,
    executer_controle_cli,
)
from shapely.geometry import LineString, MultiLineString, Point
from utils_tests import (
    construire_feature_linestring,
    construire_feature_multilinestring,
    ecrire_collection,
    ecrire_collection_avec_crs,
)

# ---------------------------------------------------------------------------
# Constantes de test : segments simples en coordonnees metriques
# ---------------------------------------------------------------------------

# Segment horizontal de (0,0) a (100,0) - longueur 100m
_COORDS_HORIZ = [[0.0, 0.0], [100.0, 0.0]]

# Meme segment horizontal - superposition totale avec _COORDS_HORIZ
_COORDS_HORIZ_IDENT = [[0.0, 0.0], [100.0, 0.0]]

# Segment horizontal de (50,0) a (150,0) - superposition partielle (50m)
_COORDS_HORIZ_DECALE = [[50.0, 0.0], [150.0, 0.0]]

# Segment horizontal de (0,0) a (40,0) - contenu dans _COORDS_HORIZ (totale)
_COORDS_HORIZ_COURT = [[0.0, 0.0], [40.0, 0.0]]

# Segment vertical de (50,-50) a (50,50) - croise _COORDS_HORIZ en un point
_COORDS_VERT = [[50.0, -50.0], [50.0, 50.0]]

# Segment 3D : memes XY que _COORDS_HORIZ mais Z differents
_COORDS_HORIZ_3D = [[0.0, 0.0, 10.0], [100.0, 0.0, 20.0]]

# Segment trop court pour etre significatif
_COORDS_MINUSCULE = [[0.0, 0.0], [0.001, 0.0]]

_NOM_FOURREAU = FICHIERS_CHEMINEMENT[0]
_NOM_PLEINE_TERRE = FICHIERS_CHEMINEMENT[1]


# ---------------------------------------------------------------------------
# Helpers de construction d'entites Shapely pour les tests unitaires
# ---------------------------------------------------------------------------


def _entite(
    coords: list[list[float]],
    couche: str = _NOM_FOURREAU,
    identifiant: str = "e1",
) -> EntiteCheminement:
    """Construit une EntiteCheminement directement depuis des coordonnees."""
    from shapely import force_2d

    geom = force_2d(LineString(coords))
    return EntiteCheminement(couche=couche, id_entite=identifiant, geometrie=geom)


# ---------------------------------------------------------------------------
# Tests de _creer_entite_depuis_feature
# ---------------------------------------------------------------------------


class TestCreerEntiteDepuisFeature:
    """Tests de la creation d'une EntiteCheminement depuis une feature GeoJSON."""

    def test_linestring_valide_retourne_entite(self) -> None:
        feature = construire_feature_linestring("f1", _COORDS_HORIZ)
        entite = _creer_entite_depuis_feature(feature, _NOM_FOURREAU)
        assert entite is not None
        assert entite.couche == _NOM_FOURREAU
        assert entite.id_entite == "f1"

    def test_geometrie_absente_retourne_none(self) -> None:
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {"id": "f1"},
            "geometry": None,
        }
        assert _creer_entite_depuis_feature(feature, _NOM_FOURREAU) is None

    def test_type_point_retourne_none(self) -> None:
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {"id": "f1"},
            "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
        }
        assert _creer_entite_depuis_feature(feature, _NOM_FOURREAU) is None

    def test_linestring_3d_acceptee_comme_2d(self) -> None:
        # Les coordonnees Z sont strippees : la geometrie 2D resultante est valide
        feature = construire_feature_linestring("f1", _COORDS_HORIZ_3D)
        entite = _creer_entite_depuis_feature(feature, _NOM_FOURREAU)
        assert entite is not None
        # La geometrie Shapely est bien 2D
        assert entite.geometrie.has_z is False

    def test_coordonnees_absentes_retourne_none(self) -> None:
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {"id": "f1"},
            "geometry": {"type": "LineString", "coordinates": []},
        }
        assert _creer_entite_depuis_feature(feature, _NOM_FOURREAU) is None

    def test_segment_trop_court_retourne_none(self) -> None:
        feature = construire_feature_linestring("f1", _COORDS_MINUSCULE)
        assert _creer_entite_depuis_feature(feature, _NOM_FOURREAU) is None

    def test_multilinestring_acceptee(self) -> None:
        feature = construire_feature_multilinestring("f1", [_COORDS_HORIZ, _COORDS_HORIZ_DECALE])
        entite = _creer_entite_depuis_feature(feature, _NOM_FOURREAU)
        assert entite is not None

    def test_identifiant_none_si_absent_des_proprietes(self) -> None:
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {},
            "geometry": {"type": "LineString", "coordinates": _COORDS_HORIZ},
        }
        entite = _creer_entite_depuis_feature(feature, _NOM_FOURREAU)
        assert entite is not None
        assert entite.id_entite is None


# ---------------------------------------------------------------------------
# Tests de charger_entites_couche
# ---------------------------------------------------------------------------


class TestChargerEntitesCouche:
    """Tests du chargement d'une couche depuis un fichier GeoJSON."""

    def test_fichier_absent_retourne_liste_vide(self, tmp_path: Any) -> None:
        chemin = str(tmp_path / "inexistant.geojson")
        entites, crs = charger_entites_couche(chemin, _NOM_FOURREAU)
        assert entites == []
        assert crs is None

    def test_fichier_valide_charge_entites(self, tmp_path: Any) -> None:
        features = [
            construire_feature_linestring("f1", _COORDS_HORIZ),
            construire_feature_linestring("f2", _COORDS_HORIZ_DECALE),
        ]
        chemin = str(tmp_path / _NOM_FOURREAU)
        ecrire_collection(chemin, features)
        entites, _ = charger_entites_couche(chemin, _NOM_FOURREAU)
        assert len(entites) == 2

    def test_crs_propage_depuis_collection(self, tmp_path: Any) -> None:
        chemin = str(tmp_path / _NOM_FOURREAU)
        ecrire_collection_avec_crs(
            chemin,
            [construire_feature_linestring("f1", _COORDS_HORIZ)],
            "EPSG:3947",
        )
        _, crs = charger_entites_couche(chemin, _NOM_FOURREAU)
        assert crs is not None
        assert "3947" in crs["properties"]["name"]

    def test_features_non_lineaires_ignorees(self, tmp_path: Any) -> None:
        features: list[dict[str, Any]] = [
            construire_feature_linestring("f1", _COORDS_HORIZ),
            {
                "type": "Feature",
                "properties": {"id": "p1"},
                "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
            },
        ]
        chemin = str(tmp_path / _NOM_FOURREAU)
        ecrire_collection(chemin, features)
        entites, _ = charger_entites_couche(chemin, _NOM_FOURREAU)
        assert len(entites) == 1

    def test_collection_vide_retourne_liste_vide(self, tmp_path: Any) -> None:
        chemin = str(tmp_path / _NOM_FOURREAU)
        ecrire_collection(chemin, [])
        entites, _ = charger_entites_couche(chemin, _NOM_FOURREAU)
        assert entites == []


# ---------------------------------------------------------------------------
# Tests de _est_chevauchement_lineaire
# ---------------------------------------------------------------------------


class TestEstChevauchementLineaire:
    """Tests de la detection du caractere lineaire et significatif d'une intersection."""

    def test_linestring_longue_est_chevauchement(self) -> None:
        geom = LineString([(0, 0), (100, 0)])
        assert _est_chevauchement_lineaire(geom) is True

    def test_point_n_est_pas_chevauchement(self) -> None:
        geom = Point(0, 0)
        assert _est_chevauchement_lineaire(geom) is False

    def test_geometrie_vide_n_est_pas_chevauchement(self) -> None:
        geom = LineString()
        assert _est_chevauchement_lineaire(geom) is False

    def test_linestring_sous_epsilon_n_est_pas_chevauchement(self) -> None:
        # Segment de 0.005m < EPSILON_LONGUEUR = 0.01m
        geom = LineString([(0, 0), (0.005, 0)])
        assert _est_chevauchement_lineaire(geom) is False

    def test_multilinestring_est_chevauchement(self) -> None:
        geom = MultiLineString([[(0, 0), (50, 0)], [(60, 0), (100, 0)]])
        assert _est_chevauchement_lineaire(geom) is True


# ---------------------------------------------------------------------------
# Tests de _classifier_superposition
# ---------------------------------------------------------------------------


class TestClassifierSuperposition:
    """Tests de la classification totale / partielle."""

    def test_chevauchement_identique_est_total(self) -> None:
        geom_a = LineString([(0, 0), (100, 0)])
        geom_b = LineString([(0, 0), (100, 0)])
        intersection = geom_a.intersection(geom_b)
        assert _classifier_superposition(intersection, geom_a, geom_b) == "totale"

    def test_chevauchement_partiel_est_partiel(self) -> None:
        geom_a = LineString([(0, 0), (100, 0)])
        geom_b = LineString([(50, 0), (150, 0)])
        intersection = geom_a.intersection(geom_b)
        # Intersection = [(50,0),(100,0)] soit 50m sur 100m = 50% < seuil
        assert _classifier_superposition(intersection, geom_a, geom_b) == "partielle"

    def test_court_contenu_dans_long_est_total(self) -> None:
        # geom_b est entierement dans geom_a -> totale pour geom_b
        geom_a = LineString([(0, 0), (100, 0)])
        geom_b = LineString([(20, 0), (80, 0)])
        intersection = geom_a.intersection(geom_b)
        # intersection = geom_b (60m), min(100, 60) = 60m, ratio = 100% >= seuil
        assert _classifier_superposition(intersection, geom_a, geom_b) == "totale"

    def test_chevauchement_juste_sous_seuil_est_partiel(self) -> None:
        # Chevauchement de 98% de la plus courte -> partielle
        geom_a = LineString([(0, 0), (100, 0)])
        geom_b = LineString([(0, 0), (50, 0)])
        # intersection ~ 50m, ratio = 50/50 = 100% -> totale
        # Testons avec un cas artificiel
        intersection = LineString([(0, 0), (48, 0)])  # 48/50 = 96% < 99%
        assert _classifier_superposition(intersection, geom_a, geom_b) == "partielle"

    def test_entite_de_longueur_negligeable_retourne_partielle(self) -> None:
        geom_a = LineString([(0, 0), (100, 0)])
        geom_minuscule = LineString([(0, 0), (0.001, 0)])
        intersection = LineString([(0, 0), (0.001, 0)])
        assert _classifier_superposition(intersection, geom_a, geom_minuscule) == "partielle"


# ---------------------------------------------------------------------------
# Tests de _analyser_paire
# ---------------------------------------------------------------------------


class TestAnalyserPaire:
    """Tests de l'analyse d'une paire d'entites."""

    def test_segments_identiques_anomalie_totale_intra(self) -> None:
        ea = _entite(_COORDS_HORIZ, couche=_NOM_FOURREAU, identifiant="a")
        eb = _entite(_COORDS_HORIZ_IDENT, couche=_NOM_FOURREAU, identifiant="b")
        anomalie = _analyser_paire(ea, eb)
        assert anomalie is not None
        assert anomalie["type_superposition"] == "totale"
        assert anomalie["niveau"] == "intra_couche"
        assert anomalie["couche_a"] == _NOM_FOURREAU
        assert anomalie["id_entite_a"] == "a"
        assert anomalie["id_entite_b"] == "b"

    def test_superposition_partielle_detectee(self) -> None:
        ea = _entite(_COORDS_HORIZ, identifiant="a")
        eb = _entite(_COORDS_HORIZ_DECALE, identifiant="b")
        anomalie = _analyser_paire(ea, eb)
        assert anomalie is not None
        assert anomalie["type_superposition"] == "partielle"
        assert anomalie["longueur_chevauchement_m"] == pytest.approx(50.0, abs=0.01)

    def test_croisement_perpendiculaire_pas_anomalie(self) -> None:
        # Les deux segments se croisent en un point -> intersection = Point -> non signale
        ea = _entite(_COORDS_HORIZ, identifiant="a")
        eb = _entite(_COORDS_VERT, identifiant="b")
        anomalie = _analyser_paire(ea, eb)
        assert anomalie is None

    def test_entites_sans_contact_pas_anomalie(self) -> None:
        ea = _entite([[0.0, 0.0], [10.0, 0.0]], identifiant="a")
        eb = _entite([[100.0, 0.0], [200.0, 0.0]], identifiant="b")
        assert _analyser_paire(ea, eb) is None

    def test_couches_differentes_niveau_inter(self) -> None:
        ea = _entite(_COORDS_HORIZ, couche=_NOM_FOURREAU, identifiant="a")
        eb = _entite(_COORDS_HORIZ_IDENT, couche=_NOM_PLEINE_TERRE, identifiant="b")
        anomalie = _analyser_paire(ea, eb)
        assert anomalie is not None
        assert anomalie["niveau"] == "inter_couches"

    def test_superposition_3d_detectee_en_2d(self) -> None:
        # Meme XY, Z differents -> superposition planimetrique detectee
        ea = _entite(_COORDS_HORIZ_3D, identifiant="a")
        eb = _entite([[0.0, 0.0, 50.0], [100.0, 0.0, 80.0]], identifiant="b")
        anomalie = _analyser_paire(ea, eb)
        assert anomalie is not None
        assert anomalie["type_superposition"] == "totale"

    def test_anomalie_contient_geometrie_intersection(self) -> None:
        ea = _entite(_COORDS_HORIZ, identifiant="a")
        eb = _entite(_COORDS_HORIZ_DECALE, identifiant="b")
        anomalie = _analyser_paire(ea, eb)
        assert anomalie is not None
        assert "geometrie_intersection" in anomalie
        geom_inter = anomalie["geometrie_intersection"]
        assert geom_inter.get("type") in (
            "LineString",
            "MultiLineString",
            "GeometryCollection",
        )


# ---------------------------------------------------------------------------
# Tests de detecter_toutes_superpositions
# ---------------------------------------------------------------------------


class TestDetecterToutesSuperpositions:
    """Tests de la detection globale intra et inter-couches."""

    def test_liste_vide_retourne_vide(self) -> None:
        assert detecter_toutes_superpositions([]) == []

    def test_une_seule_entite_retourne_vide(self) -> None:
        entites = [_entite(_COORDS_HORIZ)]
        assert detecter_toutes_superpositions(entites) == []

    def test_deux_entites_sans_superposition(self) -> None:
        entites = [
            _entite([[0.0, 0.0], [10.0, 0.0]], identifiant="a"),
            _entite([[50.0, 0.0], [60.0, 0.0]], identifiant="b"),
        ]
        assert detecter_toutes_superpositions(entites) == []

    def test_deux_entites_identiques_intra_une_anomalie(self) -> None:
        entites = [
            _entite(_COORDS_HORIZ, identifiant="a"),
            _entite(_COORDS_HORIZ_IDENT, identifiant="b"),
        ]
        anomalies = detecter_toutes_superpositions(entites)
        assert len(anomalies) == 1
        assert anomalies[0]["niveau"] == "intra_couche"

    def test_entites_couches_differentes_inter_detectee(self) -> None:
        entites = [
            _entite(_COORDS_HORIZ, couche=_NOM_FOURREAU, identifiant="a"),
            _entite(_COORDS_HORIZ_IDENT, couche=_NOM_PLEINE_TERRE, identifiant="b"),
        ]
        anomalies = detecter_toutes_superpositions(entites)
        assert len(anomalies) == 1
        assert anomalies[0]["niveau"] == "inter_couches"

    def test_croisements_non_signales(self) -> None:
        # Segments orthogonaux : intersection = point, pas lineaire
        entites = [
            _entite(_COORDS_HORIZ, identifiant="a"),
            _entite(_COORDS_VERT, identifiant="b"),
        ]
        assert detecter_toutes_superpositions(entites) == []

    def test_paires_non_dupliquees(self) -> None:
        # Trois entites dont deux paires se superposent -> 3 anomalies au maximum
        # mais chaque paire ne doit etre comptee qu'une fois
        ea = _entite(_COORDS_HORIZ, identifiant="a")
        eb = _entite(_COORDS_HORIZ_IDENT, identifiant="b")
        ec = _entite(_COORDS_HORIZ_COURT, identifiant="c")
        anomalies = detecter_toutes_superpositions([ea, eb, ec])
        # Toutes les paires se superposent : (a,b), (a,c), (b,c) → 3 anomalies
        assert len(anomalies) == 3

    def test_intra_et_inter_detectees_simultanement(self) -> None:
        entites = [
            _entite(_COORDS_HORIZ, couche=_NOM_FOURREAU, identifiant="f1"),
            _entite(_COORDS_HORIZ_IDENT, couche=_NOM_FOURREAU, identifiant="f2"),  # intra
            _entite(_COORDS_HORIZ_DECALE, couche=_NOM_PLEINE_TERRE, identifiant="p1"),  # inter
        ]
        anomalies = detecter_toutes_superpositions(entites)
        niveaux = {a["niveau"] for a in anomalies}
        assert "intra_couche" in niveaux
        assert "inter_couches" in niveaux


# ---------------------------------------------------------------------------
# Tests de construire_geojson_ecarts
# ---------------------------------------------------------------------------


class TestConstruireGeojsonEcarts:
    """Tests de la construction du GeoJSON de sortie."""

    def test_collection_vide(self) -> None:
        geojson = construire_geojson_ecarts([])
        assert geojson == {"type": "FeatureCollection", "features": []}

    def test_crs_propage_si_present(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::3947"}}
        geojson = construire_geojson_ecarts([], crs=crs)
        assert geojson["crs"] == crs

    def test_crs_absent_si_non_fourni(self) -> None:
        geojson = construire_geojson_ecarts([])
        assert "crs" not in geojson

    def test_structure_feature_anomalie(self) -> None:
        geom_inter = {"type": "LineString", "coordinates": [[50.0, 0.0], [100.0, 0.0]]}
        anomalies = [
            {
                "niveau": "intra_couche",
                "couche_a": _NOM_FOURREAU,
                "id_entite_a": "f1",
                "couche_b": _NOM_FOURREAU,
                "id_entite_b": "f2",
                "type_superposition": "partielle",
                "longueur_chevauchement_m": 50.0,
                "geometrie_intersection": geom_inter,
            }
        ]
        geojson = construire_geojson_ecarts(anomalies)
        assert len(geojson["features"]) == 1
        feature = geojson["features"][0]
        props = feature["properties"]
        assert props["niveau"] == "intra_couche"
        assert props["couche_a"] == _NOM_FOURREAU
        assert props["id_entite_a"] == "f1"
        assert props["type_superposition"] == "partielle"
        assert props["longueur_chevauchement_m"] == 50.0
        assert props["type_anomalie"] == "superposition_cheminements"
        assert props["priorite"] == PRIORITE_ANOMALIE
        assert feature["geometry"] == geom_inter

    def test_id_entite_none_conserve(self) -> None:
        geom_inter = {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 0.0]]}
        anomalies = [
            {
                "niveau": "inter_couches",
                "couche_a": _NOM_FOURREAU,
                "id_entite_a": None,
                "couche_b": _NOM_PLEINE_TERRE,
                "id_entite_b": "p1",
                "type_superposition": "totale",
                "longueur_chevauchement_m": 100.0,
                "geometrie_intersection": geom_inter,
            }
        ]
        geojson = construire_geojson_ecarts(anomalies)
        props = geojson["features"][0]["properties"]
        assert props["id_entite_a"] is None
        assert props["id_entite_b"] == "p1"


# ---------------------------------------------------------------------------
# Tests CLI bout en bout
# ---------------------------------------------------------------------------


def _ecrire_fourreau(tmp_path: Any, features: list[dict[str, Any]]) -> None:
    ecrire_collection(str(tmp_path / _NOM_FOURREAU), features)


def _ecrire_pleine_terre(tmp_path: Any, features: list[dict[str, Any]]) -> None:
    ecrire_collection(str(tmp_path / _NOM_PLEINE_TERRE), features)


@pytest.fixture
def repertoire_sans_fichiers(tmp_path: Any) -> str:
    """Repertoire vide, aucun fichier de cheminement present."""
    return str(tmp_path)


@pytest.fixture
def repertoire_intra_superposition(tmp_path: Any) -> str:
    """Fourreau avec deux entites identiques -> superposition intra-couche."""
    _ecrire_fourreau(
        tmp_path,
        [
            construire_feature_linestring("f1", _COORDS_HORIZ),
            construire_feature_linestring("f2", _COORDS_HORIZ_IDENT),
        ],
    )
    return str(tmp_path)


@pytest.fixture
def repertoire_inter_superposition(tmp_path: Any) -> str:
    """Fourreau et PleineTerre avec segments identiques -> superposition inter-couches."""
    _ecrire_fourreau(tmp_path, [construire_feature_linestring("f1", _COORDS_HORIZ)])
    _ecrire_pleine_terre(tmp_path, [construire_feature_linestring("p1", _COORDS_HORIZ_IDENT)])
    return str(tmp_path)


@pytest.fixture
def repertoire_sans_superposition(tmp_path: Any) -> str:
    """Fourreau et PleineTerre avec segments disjoints -> aucune anomalie."""
    _ecrire_fourreau(tmp_path, [construire_feature_linestring("f1", [[0.0, 0.0], [10.0, 0.0]])])
    _ecrire_pleine_terre(tmp_path, [construire_feature_linestring("p1", [[100.0, 0.0], [200.0, 0.0]])])
    return str(tmp_path)


class TestCli:
    """Tests d'integration de l'interface CLI bout en bout."""

    def test_repertoire_inexistant_retourne_erreur(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path / "inexistant"))
        assert resultat["succes"] is False
        assert "erreur" in resultat

    def test_repertoire_sans_fichiers_succes_zero_anomalies(self, repertoire_sans_fichiers: str) -> None:
        resultat = executer_controle_cli(repertoire_sans_fichiers)
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert len(resultat["fichiers_absents"]) == len(FICHIERS_CHEMINEMENT)

    def test_superposition_intra_detectee(self, repertoire_intra_superposition: str) -> None:
        resultat = executer_controle_cli(repertoire_intra_superposition)
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 1
        assert resultat["nombre_entites_analysees"] == 2
        assert resultat["priorite"] == PRIORITE_ANOMALIE

    def test_superposition_inter_detectee(self, repertoire_inter_superposition: str) -> None:
        resultat = executer_controle_cli(repertoire_inter_superposition)
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 1

    def test_aucune_superposition_zero_anomalies(self, repertoire_sans_superposition: str) -> None:
        resultat = executer_controle_cli(repertoire_sans_superposition)
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0

    def test_fichier_geojson_sortie_cree(self, repertoire_intra_superposition: str) -> None:
        executer_controle_cli(repertoire_intra_superposition)
        chemin_sortie = os.path.join(repertoire_intra_superposition, FICHIER_SORTIE)
        assert os.path.isfile(chemin_sortie)
        with open(chemin_sortie, encoding="utf-8") as fichier:
            contenu = json.load(fichier)
        assert contenu["type"] == "FeatureCollection"
        assert len(contenu["features"]) == 1

    def test_sortie_dans_repertoire_distinct(self, repertoire_intra_superposition: str, tmp_path: Any) -> None:
        dossier_sortie = str(tmp_path / "sorties")
        resultat = executer_controle_cli(repertoire_intra_superposition, dossier_sortie)
        assert resultat["succes"] is True
        assert os.path.isfile(os.path.join(dossier_sortie, FICHIER_SORTIE))

    def test_fichiers_absents_listes_dans_resultat(self, repertoire_intra_superposition: str) -> None:
        # Seul le Fourreau est present -> 3 autres fichiers signales
        resultat = executer_controle_cli(repertoire_intra_superposition)
        assert len(resultat["fichiers_absents"]) == 3

    def test_sortie_geojson_serialisable_json(self, repertoire_inter_superposition: str) -> None:
        executer_controle_cli(repertoire_inter_superposition)
        chemin = os.path.join(repertoire_inter_superposition, FICHIER_SORTIE)
        with open(chemin, encoding="utf-8") as fichier:
            contenu = json.load(fichier)
        feature = contenu["features"][0]
        props = feature["properties"]
        assert props["niveau"] == "inter_couches"
        assert props["type_anomalie"] == "superposition_cheminements"
        assert feature["geometry"]["type"] in ("LineString", "MultiLineString")
