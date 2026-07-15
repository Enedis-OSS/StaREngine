"""
Tests unitaires du controle de coherence spatiale (E301).

Couvre les cas nominaux et les cas limites :
- extraction de coordonnees pour tous les types de geometrie
- calcul du centroide et du point representatif
- regroupement par proximite (composantes connexes)
- validation du CRS projete via pyproj
- detection des groupes detaches du reseau
- construction du GeoJSON de sortie
- execution du controle en mode CLI
"""

from __future__ import annotations

import math
import os
from typing import Any

from controle_e301 import (
    NB_ENTITES_MIN,
    PRIORITE_ANOMALIE,
    SEUIL_RATTACHEMENT,
    TYPE_ANOMALIE,
    _calculer_centroide,
    _extraire_coordonnees_xy,
    _extraire_nom_crs,
    _extraire_point_representatif,
    _valider_crs_projete,
    construire_geojson_ecarts,
    detecter_anomalies_spatiales,
    executer_controle_cli,
    extraire_points_representatifs,
    regrouper_par_proximite,
)
from utils_tests import (
    construire_feature,
    ecrire_collection,
    ecrire_collection_avec_crs,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _donnee(x: float, y: float, identifiant: str = "e1") -> dict[str, Any]:
    """Construit une donnee spatiale minimale pour les tests."""
    return {
        "fichier_source": "test.geojson",
        "id_entite": identifiant,
        "type_geometrie": "Point",
        "geometrie": {"type": "Point", "coordinates": [x, y]},
        "x_rep": x,
        "y_rep": y,
    }


def _cluster_avec_outlier(
    n: int,
    x_normal: float,
    y_normal: float,
    x_outlier: float,
    y_outlier: float,
) -> list[dict[str, Any]]:
    """N points identiques au centre + 1 outlier a l'ecart."""
    donnees = [_donnee(x_normal, y_normal, f"e{i}") for i in range(n)]
    donnees.append(_donnee(x_outlier, y_outlier, "outlier"))
    return donnees


def _reseau_lineaire(n: int, pas: float) -> list[dict[str, Any]]:
    """Chaine de n points espaces de `pas` metres, alignes sur l'axe X.

    Reproduit la forme d'un reseau de distribution : lineaire et etendu, sans
    aucune position aberrante.
    """
    return [_donnee(i * pas, 0.0, f"e{i}") for i in range(n)]


# --------------------------------------------------------------------------- #
# Extraction de coordonnees
# --------------------------------------------------------------------------- #


class TestExtraireCoordonnees:
    """Tests de _extraire_coordonnees_xy pour chaque type de geometrie."""

    def test_point_retourne_une_paire(self) -> None:
        geom = {"type": "Point", "coordinates": [1.0, 2.0]}
        assert _extraire_coordonnees_xy(geom) == [(1.0, 2.0)]

    def test_linestring_retourne_toutes_les_paires(self) -> None:
        geom = {"type": "LineString", "coordinates": [[0.0, 1.0], [2.0, 3.0]]}
        assert _extraire_coordonnees_xy(geom) == [(0.0, 1.0), (2.0, 3.0)]

    def test_multipoint_retourne_toutes_les_paires(self) -> None:
        geom = {"type": "MultiPoint", "coordinates": [[1.0, 2.0], [3.0, 4.0]]}
        assert _extraire_coordonnees_xy(geom) == [(1.0, 2.0), (3.0, 4.0)]

    def test_polygon_utilise_anneau_exterieur(self) -> None:
        geom = {
            "type": "Polygon",
            "coordinates": [[[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [0.0, 0.0]]],
        }
        assert _extraire_coordonnees_xy(geom) == [
            (0.0, 0.0),
            (1.0, 0.0),
            (0.0, 1.0),
            (0.0, 0.0),
        ]

    def test_multilinestring_aplati(self) -> None:
        geom = {
            "type": "MultiLineString",
            "coordinates": [[[0.0, 0.0], [1.0, 1.0]], [[2.0, 2.0], [3.0, 3.0]]],
        }
        assert _extraire_coordonnees_xy(geom) == [
            (0.0, 0.0),
            (1.0, 1.0),
            (2.0, 2.0),
            (3.0, 3.0),
        ]

    def test_multipolygon_utilise_anneaux_exterieurs(self) -> None:
        geom = {
            "type": "MultiPolygon",
            "coordinates": [
                [[[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [0.0, 0.0]]],
                [[[5.0, 5.0], [6.0, 5.0], [5.0, 6.0], [5.0, 5.0]]],
            ],
        }
        points = _extraire_coordonnees_xy(geom)
        assert (0.0, 0.0) in points
        assert (5.0, 5.0) in points

    def test_type_inconnu_retourne_liste_vide(self) -> None:
        geom = {"type": "GeometryCollection", "coordinates": [[0.0, 0.0]]}
        assert _extraire_coordonnees_xy(geom) == []

    def test_coordonnees_absentes_retourne_liste_vide(self) -> None:
        assert _extraire_coordonnees_xy({"type": "Point"}) == []


# --------------------------------------------------------------------------- #
# Centroide et point representatif
# --------------------------------------------------------------------------- #


class TestCalculerCentroide:
    """Tests de _calculer_centroide."""

    def test_centroide_deux_points(self) -> None:
        centre = _calculer_centroide([(0.0, 0.0), (2.0, 4.0)])
        assert math.isclose(centre[0], 1.0)
        assert math.isclose(centre[1], 2.0)

    def test_centroide_point_unique(self) -> None:
        assert _calculer_centroide([(3.0, 7.0)]) == (3.0, 7.0)


class TestExtrairePointRepresentatif:
    """Tests de _extraire_point_representatif."""

    def test_point_retourne_ses_coordonnees(self) -> None:
        geom = {"type": "Point", "coordinates": [10.0, 20.0]}
        pt = _extraire_point_representatif(geom)
        assert pt is not None
        assert math.isclose(pt[0], 10.0) and math.isclose(pt[1], 20.0)

    def test_linestring_retourne_centroide(self) -> None:
        geom = {"type": "LineString", "coordinates": [[0.0, 0.0], [4.0, 2.0]]}
        pt = _extraire_point_representatif(geom)
        assert pt is not None
        assert math.isclose(pt[0], 2.0) and math.isclose(pt[1], 1.0)

    def test_type_inconnu_retourne_none(self) -> None:
        geom = {"type": "GeometryCollection", "coordinates": []}
        assert _extraire_point_representatif(geom) is None

    def test_coordonnees_absentes_retourne_none(self) -> None:
        assert _extraire_point_representatif({"type": "Point"}) is None


# --------------------------------------------------------------------------- #
# Extraction des points representatifs depuis une FeatureCollection
# --------------------------------------------------------------------------- #


class TestExtrairePointsRepresentatifs:
    """Tests de extraire_points_representatifs."""

    def test_feature_point_extrait(self) -> None:
        features = [construire_feature("e1", "Point", [1.0, 2.0])]
        donnees = extraire_points_representatifs(features, "f.geojson")
        assert len(donnees) == 1
        assert donnees[0]["id_entite"] == "e1"
        assert math.isclose(donnees[0]["x_rep"], 1.0)

    def test_feature_sans_geometrie_ignoree(self) -> None:
        features = [{"type": "Feature", "properties": {}, "geometry": None}]
        donnees = extraire_points_representatifs(features, "f.geojson")
        assert donnees == []

    def test_feature_type_geometrie_inconnu_ignoree(self) -> None:
        features = [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "GeometryCollection", "geometries": []},
            }
        ]
        donnees = extraire_points_representatifs(features, "f.geojson")
        assert donnees == []

    def test_nom_fichier_source_copie(self) -> None:
        features = [construire_feature("e1", "Point", [0.0, 0.0])]
        donnees = extraire_points_representatifs(features, "couche.geojson")
        assert donnees[0]["fichier_source"] == "couche.geojson"


# --------------------------------------------------------------------------- #
# Seuil IQR
# --------------------------------------------------------------------------- #


class TestRegrouperParProximite:
    """Tests de regrouper_par_proximite."""

    def test_points_proches_un_seul_groupe(self) -> None:
        points = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
        assert regrouper_par_proximite(points, 100.0) == [[0, 1, 2]]

    def test_transitivite_du_rattachement(self) -> None:
        """Une chaine de proche en proche forme un groupe unique.

        Les extremites sont distantes de 300 m, bien au-dela du seuil de 100 m :
        seule la transitivite les rattache.
        """
        points = [(0.0, 0.0), (90.0, 0.0), (180.0, 0.0), (270.0, 0.0)]
        groupes = regrouper_par_proximite(points, 100.0)
        assert len(groupes) == 1
        assert len(groupes[0]) == 4

    def test_deux_groupes_distants(self) -> None:
        points = [(0.0, 0.0), (10.0, 0.0), (5000.0, 0.0)]
        groupes = regrouper_par_proximite(points, 100.0)
        assert len(groupes) == 2
        assert groupes[0] == [0, 1]  # le plus nombreux en premier
        assert groupes[1] == [2]

    def test_groupes_tries_par_taille_decroissante(self) -> None:
        points = [(0.0, 0.0), (5000.0, 0.0), (5010.0, 0.0), (5020.0, 0.0)]
        groupes = regrouper_par_proximite(points, 100.0)
        assert [len(g) for g in groupes] == [3, 1]

    def test_seuil_inclusif(self) -> None:
        """Deux points exactement a la distance du seuil sont rattaches."""
        assert len(regrouper_par_proximite([(0.0, 0.0), (100.0, 0.0)], 100.0)) == 1

    def test_juste_au_dela_du_seuil_separe(self) -> None:
        assert len(regrouper_par_proximite([(0.0, 0.0), (100.01, 0.0)], 100.0)) == 2

    def test_rattachement_diagonal(self) -> None:
        """Le voisinage 3x3 de la grille couvre les cellules diagonales."""
        points = [(0.0, 0.0), (70.0, 70.0)]  # distance 99 m < 100
        assert len(regrouper_par_proximite(points, 100.0)) == 1

    def test_point_unique(self) -> None:
        assert regrouper_par_proximite([(0.0, 0.0)], 100.0) == [[0]]

    def test_aucun_point(self) -> None:
        assert regrouper_par_proximite([], 100.0) == []


# --------------------------------------------------------------------------- #
# Validation du CRS
# --------------------------------------------------------------------------- #


class TestValiderCrsProjecte:
    """Tests de _valider_crs_projete via pyproj."""

    def test_crs_projete_lambert(self) -> None:
        assert _valider_crs_projete("urn:ogc:def:crs:EPSG::3947") is True

    def test_crs_projete_epsg_direct(self) -> None:
        assert _valider_crs_projete("EPSG:2154") is True

    def test_crs_geographique_wgs84(self) -> None:
        assert _valider_crs_projete("urn:ogc:def:crs:EPSG::4326") is False

    def test_crs_invalide_retourne_false(self) -> None:
        assert _valider_crs_projete("CRS_INCONNU_XYZ") is False


# --------------------------------------------------------------------------- #
# Detection d'anomalies spatiales
# --------------------------------------------------------------------------- #


class TestDetecterAnomaliesSpatiales:
    """Tests de detecter_anomalies_spatiales."""

    def test_cluster_homogene_aucune_anomalie(self) -> None:
        donnees = [_donnee(100.0, 200.0, f"e{i}") for i in range(5)]
        anomalies, groupes = detecter_anomalies_spatiales(donnees)
        assert anomalies == []
        assert groupes == 1

    def test_outlier_extreme_detecte(self) -> None:
        """Une faute de saisie projette l'entite loin du reseau."""
        donnees = _cluster_avec_outlier(10, 100.0, 100.0, 100000.0, 100.0)
        anomalies, groupes = detecter_anomalies_spatiales(donnees)
        assert len(anomalies) == 1
        assert anomalies[0]["id_entite"] == "outlier"
        assert groupes == 2

    def test_reseau_etendu_aucune_anomalie(self) -> None:
        """Regression : un reseau lineaire etendu n'a pas de position aberrante.

        50 entites espacees de 200 m couvrent 10 km. L'ancien critere (ecart au
        median spatial + seuil de Tukey) signalait la peripherie d'un tel reseau ;
        le rattachement, lui, ne depend pas de sa forme.
        """
        donnees = _reseau_lineaire(50, 200.0)
        anomalies, groupes = detecter_anomalies_spatiales(donnees)
        assert anomalies == []
        assert groupes == 1

    def test_antenne_eloignee_reste_conforme(self) -> None:
        """Regression : une branche desservie par une antenne reste rattachee.

        Cas releve sur les jeux de reference : un groupe d'entites a 245 m du
        coeur du reseau, relie par une antenne — configuration legitime.
        """
        donnees = [_donnee(float(i), 0.0, f"coeur{i}") for i in range(20)]
        donnees += [_donnee(245.0 + i, 0.0, f"antenne{i}") for i in range(4)]
        anomalies, _ = detecter_anomalies_spatiales(donnees)
        assert anomalies == []

    def test_lot_decale_en_bloc_detecte(self) -> None:
        """Un lot d'entites decalees ensemble reste voisin de lui-meme.

        Le critere du plus proche voisin les manquerait ; le regroupement les
        detecte, leur groupe etant detache du reseau.
        """
        donnees = [_donnee(float(i), 0.0, f"e{i}") for i in range(20)]
        donnees += [_donnee(50000.0 + i, 0.0, f"decale{i}") for i in range(5)]
        anomalies, groupes = detecter_anomalies_spatiales(donnees)
        assert len(anomalies) == 5
        assert groupes == 2
        assert all(a["taille_groupe"] == 5 for a in anomalies)

    def test_retourne_le_nombre_de_groupes(self) -> None:
        donnees = [_donnee(0.0, 0.0, f"e{i}") for i in range(4)]
        _, groupes = detecter_anomalies_spatiales(donnees)
        assert groupes == 1

    def test_proprietes_anomalie_presentes(self) -> None:
        donnees = _cluster_avec_outlier(10, 0.0, 0.0, 9999.0, 0.0)
        anomalies, _ = detecter_anomalies_spatiales(donnees)
        assert len(anomalies) == 1
        a = anomalies[0]
        assert math.isclose(a["distance_m"], 9999.0, rel_tol=1e-3)
        assert a["seuil_m"] == SEUIL_RATTACHEMENT
        assert a["taille_groupe"] == 1

    def test_distance_mesuree_au_reseau(self) -> None:
        """La distance rapportee est celle qui separe le groupe du reseau."""
        donnees = [_donnee(0.0, 0.0, f"e{i}") for i in range(10)]
        donnees.append(_donnee(3000.0, 4000.0, "outlier"))
        anomalies, _ = detecter_anomalies_spatiales(donnees)
        assert math.isclose(anomalies[0]["distance_m"], 5000.0, rel_tol=1e-3)

    def test_le_groupe_majoritaire_fait_reference(self) -> None:
        """Le reseau est le groupe le plus nombreux, ou qu'il se trouve."""
        donnees = [_donnee(100000.0 + i, 0.0, f"reseau{i}") for i in range(20)]
        donnees.append(_donnee(0.0, 0.0, "isolee"))
        anomalies, _ = detecter_anomalies_spatiales(donnees)
        assert len(anomalies) == 1
        assert anomalies[0]["id_entite"] == "isolee"

    def test_seuil_personnalise(self) -> None:
        donnees = [_donnee(0.0, 0.0, f"e{i}") for i in range(5)]
        donnees.append(_donnee(1000.0, 0.0, "eloignee"))
        assert detecter_anomalies_spatiales(donnees, seuil=2000.0)[0] == []
        assert len(detecter_anomalies_spatiales(donnees, seuil=100.0)[0]) == 1


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
            "geometrie": {"type": "Point", "coordinates": [1.0, 2.0]},
            "distance_m": 999.5,
            "seuil_m": SEUIL_RATTACHEMENT,
            "taille_groupe": 3,
        }

    def test_type_feature_collection(self) -> None:
        resultat = construire_geojson_ecarts([self._anomalie()])
        assert resultat["type"] == "FeatureCollection"

    def test_properties_obligatoires(self) -> None:
        resultat = construire_geojson_ecarts([self._anomalie()])
        props = resultat["features"][0]["properties"]
        assert props["fichier_source"] == "f.geojson"
        assert props["id_entite"] == "e1"
        assert props["distance_au_reseau_m"] == 999.5
        assert props["taille_groupe"] == 3
        assert props["seuil_m"] == SEUIL_RATTACHEMENT
        assert props["type_anomalie"] == TYPE_ANOMALIE
        assert props["priorite"] == PRIORITE_ANOMALIE

    def test_geometrie_originale_conservee(self) -> None:
        resultat = construire_geojson_ecarts([self._anomalie()])
        geom = resultat["features"][0]["geometry"]
        assert geom["type"] == "Point"

    def test_sans_crs_pas_de_champ_crs(self) -> None:
        resultat = construire_geojson_ecarts([self._anomalie()])
        assert "crs" not in resultat

    def test_avec_crs_champ_present(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::3947"}}
        resultat = construire_geojson_ecarts([self._anomalie()], crs=crs)
        assert resultat["crs"] == crs

    def test_liste_vide_aucun_feature(self) -> None:
        resultat = construire_geojson_ecarts([])
        assert resultat["features"] == []


# --------------------------------------------------------------------------- #
# Extraction du nom de CRS
# --------------------------------------------------------------------------- #


class TestExtraireNomCrs:
    """Tests de _extraire_nom_crs."""

    def test_crs_valide_retourne_nom(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::3947"}}
        assert _extraire_nom_crs(crs) == "urn:ogc:def:crs:EPSG::3947"

    def test_crs_none_retourne_none(self) -> None:
        assert _extraire_nom_crs(None) is None

    def test_properties_absentes_retourne_none(self) -> None:
        assert _extraire_nom_crs({"type": "name"}) is None

    def test_nom_vide_retourne_none(self) -> None:
        assert _extraire_nom_crs({"type": "name", "properties": {"name": ""}}) is None


# --------------------------------------------------------------------------- #
# Tests d'integration du controle CLI
# --------------------------------------------------------------------------- #


class TestCli:
    """Tests de executer_controle_cli."""

    def test_repertoire_inexistant_retourne_erreur(self) -> None:
        resultat = executer_controle_cli("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_aucun_geojson_retourne_erreur(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False
        assert "GeoJSON" in resultat["erreur"]

    def test_entites_insuffisantes_retourne_erreur(self, tmp_path: Any) -> None:
        # Moins de NB_ENTITES_MIN entites (sans CRS pour eviter la validation CRS)
        nb = NB_ENTITES_MIN - 1
        features = [construire_feature(f"e{i}", "Point", [float(i), float(i)]) for i in range(nb)]
        ecrire_collection(str(tmp_path / "couche.geojson"), features)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False
        assert "insuffisant" in resultat["erreur"]

    def test_crs_non_projete_retourne_erreur(self, tmp_path: Any) -> None:
        features = [construire_feature(f"e{i}", "Point", [float(i), float(i)]) for i in range(NB_ENTITES_MIN)]
        ecrire_collection_avec_crs(str(tmp_path / "couche.geojson"), features, "EPSG:4326")
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False
        assert "projete" in resultat["erreur"]

    def test_nominal_sans_anomalie(self, tmp_path: Any) -> None:
        # 10 points identiques -> IQR=0, seuil=0, toutes distances=0 -> aucune anomalie
        features = [construire_feature(f"e{i}", "Point", [100.0, 100.0]) for i in range(10)]
        ecrire_collection_avec_crs(str(tmp_path / "couche.geojson"), features, "EPSG:3947")
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["entites_analysees"] == 10
        assert resultat["priorite"] == PRIORITE_ANOMALIE

    def test_nominal_avec_anomalie(self, tmp_path: Any) -> None:
        # 10 points en (100, 100) + 1 outlier tres eloigne
        features = [construire_feature(f"e{i}", "Point", [100.0, 100.0]) for i in range(10)]
        features.append(construire_feature("outlier", "Point", [100000.0, 100.0]))
        ecrire_collection_avec_crs(str(tmp_path / "couche.geojson"), features, "EPSG:3947")
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 1
        assert resultat["nombre_groupes"] == 2
        assert resultat["seuil_rattachement_m"] == SEUIL_RATTACHEMENT

    def test_fichier_ecarts_cree(self, tmp_path: Any) -> None:
        features = [construire_feature(f"e{i}", "Point", [float(i), 0.0]) for i in range(NB_ENTITES_MIN)]
        ecrire_collection_avec_crs(str(tmp_path / "couche.geojson"), features, "EPSG:3947")
        executer_controle_cli(str(tmp_path))
        assert os.path.isfile(str(tmp_path / "ecarts_coherence_spatiale.geojson"))

    def test_rapport_contient_champs_obligatoires(self, tmp_path: Any) -> None:
        features = [construire_feature(f"e{i}", "Point", [float(i), 0.0]) for i in range(NB_ENTITES_MIN)]
        ecrire_collection_avec_crs(str(tmp_path / "couche.geojson"), features, "EPSG:3947")
        resultat = executer_controle_cli(str(tmp_path))
        for champ in (
            "succes",
            "priorite",
            "nombre_anomalies",
            "entites_analysees",
            "fichiers_analyses",
            "nombre_groupes",
            "seuil_rattachement_m",
            "sortie",
        ):
            assert champ in resultat, f"Champ manquant : {champ}"

    def test_dossier_sortie_distinct(self, tmp_path: Any) -> None:
        features = [construire_feature(f"e{i}", "Point", [float(i), 0.0]) for i in range(NB_ENTITES_MIN)]
        ecrire_collection_avec_crs(str(tmp_path / "couche.geojson"), features, "EPSG:3947")
        dossier_sortie = str(tmp_path / "sortie")
        executer_controle_cli(str(tmp_path), dossier_sortie)
        assert os.path.isfile(os.path.join(dossier_sortie, "ecarts_coherence_spatiale.geojson"))

    def test_sans_crs_controle_tolere(self, tmp_path: Any) -> None:
        # Pas de CRS dans le fichier : la validation CRS est ignoree
        features = [construire_feature(f"e{i}", "Point", [float(i), 0.0]) for i in range(NB_ENTITES_MIN)]
        ecrire_collection(str(tmp_path / "couche.geojson"), features)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
