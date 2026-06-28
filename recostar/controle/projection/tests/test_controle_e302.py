"""
Tests unitaires du controle de superficie des geometries supplementaires (E302).

Couvre les cas nominaux et les cas limites :
- calcul de l'aire par la formule de Shoelace (anneau, polygon, multipolygon)
- dispatcher par type de geometrie
- detection d'entites trop grandes (seuil 100 m²)
- construction du GeoJSON de sortie
- execution du controle en mode CLI
"""

from __future__ import annotations

import math
import os
from typing import Any

from controle_e302 import (
    NOM_FICHIER_CIBLE,
    PRIORITE_ANOMALIE,
    SEUIL_AIRE_M2,
    _aire_anneau,
    _aire_multipolygon,
    _aire_polygon,
    calculer_aire_m2,
    construire_geojson_ecarts,
    detecter_entites_trop_grandes,
    executer_controle_cli,
)
from utils_tests import (
    construire_feature,
    ecrire_collection,
    ecrire_collection_avec_crs,
)

# --------------------------------------------------------------------------- #
# Helpers geometriques
# --------------------------------------------------------------------------- #


def _carre(cote: float, origine: float = 0.0) -> list[list[float]]:
    """Anneau carre ferme de cote donne, en partant de (origine, origine)."""
    o = origine
    c = origine + cote
    return [[o, o], [c, o], [c, c], [o, c], [o, o]]


def _feature_polygon(identifiant: str, cote: float) -> dict[str, Any]:
    """Feature GeoJSON de type Polygon carre de superficie cote² m²."""
    return construire_feature(identifiant, "Polygon", [_carre(cote)])


def _ecrire_cible(
    chemin_repertoire: str,
    features: list[dict[str, Any]],
    epsg: str | None = None,
) -> None:
    """Ecrit le fichier cible RPD_GeometrieSupplementaire_Reco.geojson."""
    chemin = os.path.join(chemin_repertoire, NOM_FICHIER_CIBLE)
    if epsg is not None:
        ecrire_collection_avec_crs(chemin, features, epsg)
    else:
        ecrire_collection(chemin, features)


# --------------------------------------------------------------------------- #
# Formule de Shoelace — anneau
# --------------------------------------------------------------------------- #


class TestAireAnneau:
    """Tests de _aire_anneau (formule de Shoelace)."""

    def test_carre_10m_aire_100(self) -> None:
        assert math.isclose(_aire_anneau(_carre(10.0)), 100.0)

    def test_carre_20m_aire_400(self) -> None:
        assert math.isclose(_aire_anneau(_carre(20.0)), 400.0)

    def test_triangle_rectangle(self) -> None:
        # Triangle rectangle base=6, hauteur=4 -> aire=12
        anneau = [[0.0, 0.0], [6.0, 0.0], [0.0, 4.0], [0.0, 0.0]]
        assert math.isclose(_aire_anneau(anneau), 12.0)

    def test_anneau_vide_aire_nulle(self) -> None:
        assert math.isclose(_aire_anneau([]), 0.0)

    def test_insensible_orientation_sens_horaire(self) -> None:
        # Meme carre, sommets dans le sens inverse -> meme aire
        anneau_inverse = list(reversed(_carre(10.0)))
        assert math.isclose(_aire_anneau(anneau_inverse), 100.0)


# --------------------------------------------------------------------------- #
# Polygon avec trous
# --------------------------------------------------------------------------- #


class TestAirePolygon:
    """Tests de _aire_polygon."""

    def test_polygon_sans_trou(self) -> None:
        assert math.isclose(_aire_polygon([_carre(10.0)]), 100.0)

    def test_polygon_avec_trou(self) -> None:
        # Carre 20m x 20m (400 m²) moins trou 5m x 5m (25 m²) = 375 m²
        exterieur = _carre(20.0)
        interieur = _carre(5.0, origine=7.5)
        assert math.isclose(_aire_polygon([exterieur, interieur]), 375.0)

    def test_polygon_trou_egal_exterieur_aire_nulle(self) -> None:
        # Trou identique a l'exterieur -> aire = 0
        anneau = _carre(10.0)
        assert math.isclose(_aire_polygon([anneau, anneau]), 0.0)


# --------------------------------------------------------------------------- #
# MultiPolygon
# --------------------------------------------------------------------------- #


class TestAireMultipolygon:
    """Tests de _aire_multipolygon."""

    def test_deux_carres_10m(self) -> None:
        poly1 = [_carre(10.0)]
        poly2 = [_carre(10.0, origine=20.0)]
        assert math.isclose(_aire_multipolygon([poly1, poly2]), 200.0)

    def test_un_seul_polygon(self) -> None:
        assert math.isclose(_aire_multipolygon([[_carre(7.0)]]), 49.0)


# --------------------------------------------------------------------------- #
# Dispatcher calculer_aire_m2
# --------------------------------------------------------------------------- #


class TestCalculerAireM2:
    """Tests de calculer_aire_m2 pour chaque type de geometrie."""

    def test_polygon_retourne_aire(self) -> None:
        geom = {"type": "Polygon", "coordinates": [_carre(10.0)]}
        aire = calculer_aire_m2(geom)
        assert aire is not None and math.isclose(aire, 100.0)

    def test_multipolygon_retourne_aire(self) -> None:
        geom = {
            "type": "MultiPolygon",
            "coordinates": [[_carre(5.0)], [_carre(5.0, origine=10.0)]],
        }
        aire = calculer_aire_m2(geom)
        assert aire is not None and math.isclose(aire, 50.0)

    def test_point_retourne_none(self) -> None:
        assert calculer_aire_m2({"type": "Point", "coordinates": [0.0, 0.0]}) is None

    def test_linestring_retourne_none(self) -> None:
        geom = {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 1.0]]}
        assert calculer_aire_m2(geom) is None

    def test_type_inconnu_retourne_none(self) -> None:
        assert calculer_aire_m2({"type": "GeometryCollection"}) is None

    def test_coordonnees_absentes_retourne_none(self) -> None:
        assert calculer_aire_m2({"type": "Polygon"}) is None

    def test_coordonnees_vides_retourne_none(self) -> None:
        assert calculer_aire_m2({"type": "Polygon", "coordinates": []}) is None


# --------------------------------------------------------------------------- #
# Detection des entites trop grandes
# --------------------------------------------------------------------------- #


class TestDetecterEntitiesTopGrandes:
    """Tests de detecter_entites_trop_grandes."""

    def test_entite_conforme_non_signalee(self) -> None:
        # 10m x 10m = exactement 100 m² -> non detecete (condition stricte > 100)
        features = [_feature_polygon("e1", 10.0)]
        anomalies, nb = detecter_entites_trop_grandes(features, "f.geojson")
        assert anomalies == []
        assert nb == 1

    def test_entite_trop_grande_signalee(self) -> None:
        features = [_feature_polygon("e1", 20.0)]  # 400 m²
        anomalies, _ = detecter_entites_trop_grandes(features, "f.geojson")
        assert len(anomalies) == 1
        assert anomalies[0]["id_entite"] == "e1"
        assert math.isclose(anomalies[0]["aire_m2"], 400.0)

    def test_entite_sans_geometrie_ignoree(self) -> None:
        features = [{"type": "Feature", "properties": {}, "geometry": None}]
        anomalies, nb = detecter_entites_trop_grandes(features, "f.geojson")
        assert anomalies == []
        assert nb == 0

    def test_point_ignore_pas_comptabilise(self) -> None:
        features = [construire_feature("e1", "Point", [0.0, 0.0])]
        anomalies, nb = detecter_entites_trop_grandes(features, "f.geojson")
        assert anomalies == []
        assert nb == 0

    def test_nb_entites_analysees_correct(self) -> None:
        features = [
            _feature_polygon("e1", 5.0),  # 25 m² -> conforme
            _feature_polygon("e2", 20.0),  # 400 m² -> anomalie
            construire_feature("e3", "Point", [0.0, 0.0]),  # ignoree
        ]
        anomalies, nb = detecter_entites_trop_grandes(features, "f.geojson")
        assert len(anomalies) == 1
        assert nb == 2

    def test_seuil_strict_101m2_detecte(self) -> None:
        # Carre de cote sqrt(101) ~ 10.05m -> aire > 100
        import math as _math

        cote = _math.sqrt(101.0)
        features = [_feature_polygon("e1", cote)]
        anomalies, _ = detecter_entites_trop_grandes(features, "f.geojson")
        assert len(anomalies) == 1

    def test_nom_fichier_source_copie(self) -> None:
        features = [_feature_polygon("e1", 20.0)]
        anomalies, _ = detecter_entites_trop_grandes(features, "cible.geojson")
        assert anomalies[0]["fichier_source"] == "cible.geojson"


# --------------------------------------------------------------------------- #
# Construction du GeoJSON de sortie
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de construire_geojson_ecarts."""

    def _anomalie(self) -> dict[str, Any]:
        return {
            "fichier_source": "f.geojson",
            "id_entite": "e1",
            "type_geometrie": "Polygon",
            "geometrie": {"type": "Polygon", "coordinates": [_carre(20.0)]},
            "aire_m2": 400.0,
        }

    def test_type_feature_collection(self) -> None:
        assert construire_geojson_ecarts([self._anomalie()])["type"] == "FeatureCollection"

    def test_properties_obligatoires(self) -> None:
        props = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert props["aire_m2"] == 400.0
        assert props["seuil_m2"] == SEUIL_AIRE_M2
        assert props["type_anomalie"] == "aire_excessive"
        assert props["priorite"] == PRIORITE_ANOMALIE

    def test_geometrie_originale_conservee(self) -> None:
        geom = construire_geojson_ecarts([self._anomalie()])["features"][0]["geometry"]
        assert geom["type"] == "Polygon"

    def test_sans_crs_pas_de_champ_crs(self) -> None:
        assert "crs" not in construire_geojson_ecarts([self._anomalie()])

    def test_avec_crs_champ_present(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::3947"}}
        resultat = construire_geojson_ecarts([self._anomalie()], crs=crs)
        assert resultat["crs"] == crs

    def test_liste_vide(self) -> None:
        assert construire_geojson_ecarts([])["features"] == []


# --------------------------------------------------------------------------- #
# Tests d'integration du controle CLI
# --------------------------------------------------------------------------- #


class TestCli:
    """Tests de executer_controle_cli."""

    def test_repertoire_inexistant(self) -> None:
        resultat = executer_controle_cli("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_fichier_cible_absent(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False
        assert NOM_FICHIER_CIBLE in resultat["erreur"]

    def test_nominal_sans_anomalie(self, tmp_path: Any) -> None:
        # Entite de 5m x 5m = 25 m² -> sous le seuil
        features = [_feature_polygon("e1", 5.0)]
        _ecrire_cible(str(tmp_path), features, "EPSG:3947")
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 0
        assert resultat["entites_analysees"] == 1

    def test_nominal_avec_anomalie(self, tmp_path: Any) -> None:
        # Entite de 20m x 20m = 400 m² -> depasse le seuil
        features = [_feature_polygon("e1", 20.0)]
        _ecrire_cible(str(tmp_path), features, "EPSG:3947")
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 1

    def test_plusieurs_entites_mixtes(self, tmp_path: Any) -> None:
        features = [
            _feature_polygon("conforme", 5.0),  # 25 m²
            _feature_polygon("trop_grand", 20.0),  # 400 m²
        ]
        _ecrire_cible(str(tmp_path), features)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 1
        assert resultat["entites_analysees"] == 2

    def test_fichier_ecarts_cree(self, tmp_path: Any) -> None:
        _ecrire_cible(str(tmp_path), [_feature_polygon("e1", 5.0)])
        executer_controle_cli(str(tmp_path))
        assert os.path.isfile(os.path.join(str(tmp_path), "ecarts_geometrie_supplementaire.geojson"))

    def test_rapport_contient_champs_obligatoires(self, tmp_path: Any) -> None:
        _ecrire_cible(str(tmp_path), [_feature_polygon("e1", 5.0)])
        resultat = executer_controle_cli(str(tmp_path))
        for champ in (
            "succes",
            "priorite",
            "nombre_anomalies",
            "entites_analysees",
            "seuil_aire_m2",
            "sortie",
        ):
            assert champ in resultat, f"Champ manquant : {champ}"

    def test_seuil_aire_m2_dans_rapport(self, tmp_path: Any) -> None:
        _ecrire_cible(str(tmp_path), [_feature_polygon("e1", 5.0)])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["seuil_aire_m2"] == SEUIL_AIRE_M2

    def test_dossier_sortie_distinct(self, tmp_path: Any) -> None:
        _ecrire_cible(str(tmp_path), [_feature_polygon("e1", 5.0)])
        dossier_sortie = str(tmp_path / "sortie")
        executer_controle_cli(str(tmp_path), dossier_sortie)
        assert os.path.isfile(os.path.join(dossier_sortie, "ecarts_geometrie_supplementaire.geojson"))

    def test_priorite_bloquant(self, tmp_path: Any) -> None:
        _ecrire_cible(str(tmp_path), [_feature_polygon("e1", 5.0)])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["priorite"] == "bloquant"

    def test_entite_exactement_100m2_non_detectee(self, tmp_path: Any) -> None:
        # 10m x 10m = exactement 100 m² -> conforme (seuil strict)
        features = [_feature_polygon("e1", 10.0)]
        _ecrire_cible(str(tmp_path), features)
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0
