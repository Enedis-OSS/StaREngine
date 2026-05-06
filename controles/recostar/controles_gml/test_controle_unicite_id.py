"""Tests unitaires pour le controle d'unicite des identifiants."""

import json
import os
from typing import Any

import pytest

from controle_unicite_id import (
    FICHIER_ECARTS_GEOJSON,
    FICHIER_RAPPORT_JSON,
    collecter_ids_et_doublons,
    construire_anomalies,
    construire_geojson_ecarts,
    construire_rapport_json,
    executer_controle_cli,
    lire_geojson,
    lister_fichiers_rpd,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _creer_geojson(
    features: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Cree un dict GeoJSON FeatureCollection minimal."""
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return resultat


def _creer_feature(
    id_val: str | None,
    geometrie: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Cree une feature GeoJSON minimale avec un id dans properties."""
    props: dict[str, Any] = {}
    if id_val is not None:
        props["id"] = id_val
    return {
        "type": "Feature",
        "properties": props,
        "geometry": geometrie or {"type": "Point", "coordinates": [0.0, 0.0]},
    }


def _ecrire_geojson(
    chemin: str,
    features: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> None:
    """Ecrit un fichier GeoJSON minimal."""
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(_creer_geojson(features, crs), f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# TestListerFichiersRpd
# ---------------------------------------------------------------------------
class TestListerFichiersRpd:
    """Tests pour la fonction lister_fichiers_rpd."""

    def test_repertoire_vide(self, tmp_path: Any) -> None:
        """Repertoire sans fichier RPD_ retourne une liste vide."""
        assert lister_fichiers_rpd(str(tmp_path)) == []

    def test_repertoire_inexistant(self) -> None:
        """Repertoire inexistant retourne une liste vide."""
        assert lister_fichiers_rpd("/chemin/inexistant") == []

    def test_filtre_prefixe_rpd(self, tmp_path: Any) -> None:
        """Seuls les fichiers prefixes par RPD_ et .geojson sont retenus."""
        (tmp_path / "RPD_Cable.geojson").write_text("{}", encoding="utf-8")
        (tmp_path / "RPD_Terre.geojson").write_text("{}", encoding="utf-8")
        (tmp_path / "autre.geojson").write_text("{}", encoding="utf-8")
        (tmp_path / "RPD_Cable.json").write_text("{}", encoding="utf-8")
        resultat = lister_fichiers_rpd(str(tmp_path))
        assert resultat == ["RPD_Cable.geojson", "RPD_Terre.geojson"]

    def test_tri_alphabetique(self, tmp_path: Any) -> None:
        """Les fichiers sont retournes tries par ordre alphabetique."""
        (tmp_path / "RPD_Z.geojson").write_text("{}", encoding="utf-8")
        (tmp_path / "RPD_A.geojson").write_text("{}", encoding="utf-8")
        (tmp_path / "RPD_M.geojson").write_text("{}", encoding="utf-8")
        resultat = lister_fichiers_rpd(str(tmp_path))
        assert resultat == ["RPD_A.geojson", "RPD_M.geojson", "RPD_Z.geojson"]


# ---------------------------------------------------------------------------
# TestLireGeojson
# ---------------------------------------------------------------------------
class TestLireGeojson:
    """Tests pour la fonction lire_geojson."""

    def test_fichier_existant(self, tmp_path: Any) -> None:
        """Un fichier GeoJSON valide est correctement lu."""
        chemin = str(tmp_path / "test.geojson")
        _ecrire_geojson(chemin, [_creer_feature("id1")])
        resultat = lire_geojson(chemin)
        assert resultat is not None
        assert resultat["type"] == "FeatureCollection"

    def test_fichier_absent(self) -> None:
        """Un fichier absent retourne None."""
        assert lire_geojson("/chemin/inexistant.geojson") is None


# ---------------------------------------------------------------------------
# TestCollecterIdsEtDoublons
# ---------------------------------------------------------------------------
class TestCollecterIdsEtDoublons:
    """Tests pour la fonction collecter_ids_et_doublons."""

    def test_aucun_doublon(self, tmp_path: Any) -> None:
        """Fichiers sans doublons retournent un dict vide."""
        _ecrire_geojson(
            str(tmp_path / "RPD_A.geojson"),
            [_creer_feature("id1"), _creer_feature("id2")],
        )
        doublons, total, _ = collecter_ids_et_doublons(str(tmp_path), ["RPD_A.geojson"])
        assert doublons == {}
        assert total == 2

    def test_doublons_dans_un_fichier(self, tmp_path: Any) -> None:
        """Deux features avec le meme id dans un fichier sont detectees."""
        _ecrire_geojson(
            str(tmp_path / "RPD_A.geojson"),
            [_creer_feature("id1"), _creer_feature("id1")],
        )
        doublons, total, _ = collecter_ids_et_doublons(str(tmp_path), ["RPD_A.geojson"])
        assert "id1" in doublons
        assert len(doublons["id1"]) == 2
        assert total == 2

    def test_doublons_entre_fichiers(self, tmp_path: Any) -> None:
        """Un id present dans deux fichiers differents est detecte."""
        _ecrire_geojson(
            str(tmp_path / "RPD_A.geojson"),
            [_creer_feature("id_commun")],
        )
        _ecrire_geojson(
            str(tmp_path / "RPD_B.geojson"),
            [_creer_feature("id_commun")],
        )
        doublons, total, _ = collecter_ids_et_doublons(
            str(tmp_path), ["RPD_A.geojson", "RPD_B.geojson"]
        )
        assert "id_commun" in doublons
        assert len(doublons["id_commun"]) == 2
        assert total == 2

    def test_feature_sans_id_ignoree(self, tmp_path: Any) -> None:
        """Les features sans id ne sont pas comptabilisees dans les doublons."""
        _ecrire_geojson(
            str(tmp_path / "RPD_A.geojson"),
            [_creer_feature(None), _creer_feature("id1")],
        )
        doublons, total, _ = collecter_ids_et_doublons(str(tmp_path), ["RPD_A.geojson"])
        assert doublons == {}
        assert total == 2

    def test_propagation_crs(self, tmp_path: Any) -> None:
        """Le CRS du premier fichier est propage."""
        crs_attendu = {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::2154"},
        }
        _ecrire_geojson(
            str(tmp_path / "RPD_A.geojson"),
            [_creer_feature("id1")],
            crs=crs_attendu,
        )
        _, _, crs = collecter_ids_et_doublons(str(tmp_path), ["RPD_A.geojson"])
        assert crs == crs_attendu

    def test_fichier_absent_ignore(self, tmp_path: Any) -> None:
        """Un fichier absent dans la liste est ignore sans erreur."""
        doublons, total, _ = collecter_ids_et_doublons(
            str(tmp_path), ["RPD_Inexistant.geojson"]
        )
        assert doublons == {}
        assert total == 0


# ---------------------------------------------------------------------------
# TestConstruireAnomalies
# ---------------------------------------------------------------------------
class TestConstruireAnomalies:
    """Tests pour la fonction construire_anomalies."""

    def test_aucun_doublon(self) -> None:
        """Aucun doublon produit une liste vide."""
        assert construire_anomalies({}) == []

    def test_un_doublon(self) -> None:
        """Un doublon produit une anomalie avec les bonnes proprietes."""
        doublons = {
            "id1": [
                {"nom_fichier": "RPD_A.geojson", "feature": _creer_feature("id1")},
                {"nom_fichier": "RPD_B.geojson", "feature": _creer_feature("id1")},
            ]
        }
        anomalies = construire_anomalies(doublons)
        assert len(anomalies) == 1
        assert anomalies[0]["id_duplique"] == "id1"
        assert anomalies[0]["nombre_occurrences"] == 2
        assert "RPD_A.geojson" in anomalies[0]["fichiers"]
        assert "RPD_B.geojson" in anomalies[0]["fichiers"]
        assert "id1" in anomalies[0]["message"]


# ---------------------------------------------------------------------------
# TestConstruireRapportJson
# ---------------------------------------------------------------------------
class TestConstruireRapportJson:
    """Tests pour la fonction construire_rapport_json."""

    def test_rapport_sans_anomalie(self) -> None:
        """Le rapport sans anomalie indique zero doublons et non bloquant."""
        rapport = construire_rapport_json([], 5, 100)
        assert rapport["nombre_ids_dupliques"] == 0
        assert rapport["nombre_anomalies"] == 0
        assert rapport["bloquant"] is False
        assert rapport["nombre_fichiers_analyses"] == 5
        assert rapport["nombre_features_total"] == 100

    def test_rapport_avec_anomalies(self) -> None:
        """Le rapport avec anomalies est bloquant et reporte les bonnes valeurs."""
        doublons = {
            "id1": [
                {"nom_fichier": "RPD_A.geojson", "feature": _creer_feature("id1")},
                {"nom_fichier": "RPD_A.geojson", "feature": _creer_feature("id1")},
                {"nom_fichier": "RPD_B.geojson", "feature": _creer_feature("id1")},
            ]
        }
        anomalies = construire_anomalies(doublons)
        rapport = construire_rapport_json(anomalies, 2, 50)
        assert rapport["bloquant"] is True
        assert rapport["nombre_ids_dupliques"] == 1
        assert rapport["nombre_occurrences_doublons"] == 3
        assert len(rapport["anomalies"]) == 1


# ---------------------------------------------------------------------------
# TestConstruireGeojsonEcarts
# ---------------------------------------------------------------------------
class TestConstruireGeojsonEcarts:
    """Tests pour la fonction construire_geojson_ecarts."""

    def test_geojson_vide(self) -> None:
        """Aucune anomalie produit un FeatureCollection vide."""
        geojson = construire_geojson_ecarts([])
        assert geojson["type"] == "FeatureCollection"
        assert geojson["features"] == []

    def test_geojson_avec_doublons(self) -> None:
        """Chaque occurrence d'un doublon genere une feature dans le GeoJSON."""
        doublons = {
            "id1": [
                {"nom_fichier": "RPD_A.geojson", "feature": _creer_feature("id1")},
                {"nom_fichier": "RPD_B.geojson", "feature": _creer_feature("id1")},
            ]
        }
        anomalies = construire_anomalies(doublons)
        geojson = construire_geojson_ecarts(anomalies)
        features = geojson["features"]
        assert len(features) == 2
        assert features[0]["properties"]["id_duplique"] == "id1"
        assert features[0]["properties"]["type_anomalie"] == "id_duplique"
        assert features[0]["properties"]["priorite"] == "bloquant"
        assert features[0]["properties"]["fichier_source"] == "RPD_A.geojson"
        assert features[1]["properties"]["fichier_source"] == "RPD_B.geojson"

    def test_propagation_crs(self) -> None:
        """Le CRS est propage dans le GeoJSON de sortie."""
        crs = {"type": "name", "properties": {"name": "EPSG:2154"}}
        geojson = construire_geojson_ecarts([], crs=crs)
        assert geojson["crs"] == crs

    def test_sans_crs(self) -> None:
        """Sans CRS, le champ crs est absent du GeoJSON."""
        geojson = construire_geojson_ecarts([])
        assert "crs" not in geojson


# ---------------------------------------------------------------------------
# TestExecuterControleCli
# ---------------------------------------------------------------------------
class TestExecuterControleCli:
    """Tests d'integration pour executer_controle_cli."""

    def test_repertoire_inexistant(self) -> None:
        """Un repertoire inexistant retourne une erreur."""
        resultat = executer_controle_cli("/chemin/inexistant")
        assert resultat["succes"] is False

    def test_repertoire_sans_fichiers(self, tmp_path: Any) -> None:
        """Un repertoire sans fichiers RPD_ retourne une erreur."""
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is False

    def test_sans_doublon(self, tmp_path: Any) -> None:
        """Pas de doublon : succes, rapport et ecarts generes."""
        _ecrire_geojson(
            str(tmp_path / "RPD_A.geojson"),
            [_creer_feature("id1"), _creer_feature("id2")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert os.path.isfile(resultat["rapport"])
        assert os.path.isfile(resultat["ecarts"])

        with open(resultat["rapport"], "r", encoding="utf-8") as f:
            rapport = json.load(f)
        assert rapport["nombre_ids_dupliques"] == 0

    def test_avec_doublons(self, tmp_path: Any) -> None:
        """Doublons detectes : les fichiers de sortie contiennent les anomalies."""
        _ecrire_geojson(
            str(tmp_path / "RPD_A.geojson"),
            [_creer_feature("id1"), _creer_feature("id1")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True

        with open(resultat["rapport"], "r", encoding="utf-8") as f:
            rapport = json.load(f)
        assert rapport["nombre_ids_dupliques"] == 1
        assert rapport["bloquant"] is True

        with open(resultat["ecarts"], "r", encoding="utf-8") as f:
            ecarts = json.load(f)
        assert len(ecarts["features"]) == 2

    def test_sortie_dans_repertoire_dedie(self, tmp_path: Any) -> None:
        """Les fichiers de sortie sont generes dans le repertoire de sortie."""
        entree = tmp_path / "entree"
        entree.mkdir()
        sortie = tmp_path / "sortie"

        _ecrire_geojson(
            str(entree / "RPD_A.geojson"),
            [_creer_feature("id1")],
        )
        resultat = executer_controle_cli(str(entree), str(sortie))
        assert resultat["succes"] is True
        assert os.path.isfile(os.path.join(str(sortie), FICHIER_RAPPORT_JSON))
        assert os.path.isfile(os.path.join(str(sortie), FICHIER_ECARTS_GEOJSON))

    def test_doublons_entre_fichiers(self, tmp_path: Any) -> None:
        """Un id present dans deux fichiers differents est detecte."""
        _ecrire_geojson(
            str(tmp_path / "RPD_A.geojson"),
            [_creer_feature("id_commun")],
        )
        _ecrire_geojson(
            str(tmp_path / "RPD_B.geojson"),
            [_creer_feature("id_commun")],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True

        with open(resultat["rapport"], "r", encoding="utf-8") as f:
            rapport = json.load(f)
        assert rapport["nombre_ids_dupliques"] == 1
        assert rapport["nombre_occurrences_doublons"] == 2

    def test_features_sans_id_non_comptees(self, tmp_path: Any) -> None:
        """Les features sans id ne sont pas comptees dans les doublons."""
        _ecrire_geojson(
            str(tmp_path / "RPD_A.geojson"),
            [_creer_feature(None), _creer_feature(None)],
        )
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True

        with open(resultat["rapport"], "r", encoding="utf-8") as f:
            rapport = json.load(f)
        assert rapport["nombre_ids_dupliques"] == 0
