"""
Tests unitaires du module utils_geojson.

Couvre les fonctions partagees par tous les controles altimetriques :
lecture, ecriture, listage de fichiers et extraction d'identifiant.
"""

import json
import os
from typing import Any

from utils_geojson import (
    EXTENSION_GEOJSON,
    PREFIXE_ECARTS,
    ecrire_geojson,
    lire_geojson,
    lister_fichiers_geojson,
    obtenir_id_feature,
)

# --------------------------------------------------------------------------- #
# Tests de lire_geojson
# --------------------------------------------------------------------------- #


class TestLireGeojson:
    """Tests de la lecture de fichiers GeoJSON."""

    def test_charge_fichier_existant(self, tmp_path: Any) -> None:
        chemin = str(tmp_path / "data.geojson")
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": []}, f)
        contenu = lire_geojson(chemin)
        assert contenu is not None
        assert contenu["type"] == "FeatureCollection"

    def test_retourne_none_si_absent(self, tmp_path: Any) -> None:
        chemin = str(tmp_path / "inexistant.geojson")
        assert lire_geojson(chemin) is None


# --------------------------------------------------------------------------- #
# Tests de ecrire_geojson
# --------------------------------------------------------------------------- #


class TestEcrireGeojson:
    """Tests de l'ecriture de fichiers GeoJSON."""

    def test_cree_fichier_valide(self, tmp_path: Any) -> None:
        chemin = str(tmp_path / "sortie.geojson")
        donnees = {"type": "FeatureCollection", "features": []}
        ecrire_geojson(donnees, chemin)
        assert os.path.isfile(chemin)
        with open(chemin, encoding="utf-8") as f:
            contenu = json.load(f)
        assert contenu == donnees


# --------------------------------------------------------------------------- #
# Tests de lister_fichiers_geojson
# --------------------------------------------------------------------------- #


class TestListerFichiersGeojson:
    """Tests du listing et filtrage des fichiers GeoJSON."""

    def test_liste_fichiers_eligibles(self, tmp_path: Any) -> None:
        (tmp_path / "donnees.geojson").write_text("{}", encoding="utf-8")
        fichiers = lister_fichiers_geojson(str(tmp_path))
        assert "donnees.geojson" in fichiers

    def test_exclut_fichiers_ecarts(self, tmp_path: Any) -> None:
        (tmp_path / "donnees.geojson").write_text("{}", encoding="utf-8")
        (tmp_path / "ecarts_3d.geojson").write_text("{}", encoding="utf-8")
        fichiers = lister_fichiers_geojson(str(tmp_path))
        assert "donnees.geojson" in fichiers
        assert "ecarts_3d.geojson" not in fichiers

    def test_exclut_non_geojson(self, tmp_path: Any) -> None:
        (tmp_path / "donnees.geojson").write_text("{}", encoding="utf-8")
        (tmp_path / "readme.txt").write_text("texte", encoding="utf-8")
        fichiers = lister_fichiers_geojson(str(tmp_path))
        assert len(fichiers) == 1

    def test_retourne_liste_triee(self, tmp_path: Any) -> None:
        (tmp_path / "b.geojson").write_text("{}", encoding="utf-8")
        (tmp_path / "a.geojson").write_text("{}", encoding="utf-8")
        fichiers = lister_fichiers_geojson(str(tmp_path))
        assert fichiers == ["a.geojson", "b.geojson"]

    def test_repertoire_vide(self, tmp_path: Any) -> None:
        assert lister_fichiers_geojson(str(tmp_path)) == []

    def test_constantes_coherentes(self) -> None:
        assert EXTENSION_GEOJSON == ".geojson"
        assert PREFIXE_ECARTS == "ecarts_"


# --------------------------------------------------------------------------- #
# Tests de obtenir_id_feature
# --------------------------------------------------------------------------- #


class TestObtenirIdFeature:
    """Tests de l'extraction de l'identifiant metier d'une feature."""

    def test_id_chaine(self) -> None:
        feature: dict[str, Any] = {"properties": {"id": "abc"}}
        assert obtenir_id_feature(feature) == "abc"

    def test_id_entier(self) -> None:
        feature: dict[str, Any] = {"properties": {"id": 42}}
        assert obtenir_id_feature(feature) == "42"

    def test_id_absent(self) -> None:
        feature: dict[str, Any] = {"properties": {}}
        assert obtenir_id_feature(feature) is None

    def test_properties_absentes(self) -> None:
        feature: dict[str, Any] = {}
        assert obtenir_id_feature(feature) is None

    def test_properties_nulles(self) -> None:
        feature: dict[str, Any] = {"properties": None}
        assert obtenir_id_feature(feature) is None
