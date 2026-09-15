"""
Tests du chargement des couches GeoJSON (fonctions_communes/chargement.py).

Ces fonctions sont communes a de nombreux controles ; leurs tests les
suivent ici. La distinction couche **absente** / couche **vide** est la propriete
la plus sensible : onze controles en dependent pour decider s'ils signalent une
donnee manquante ou s'ils ne trouvent simplement aucune anomalie.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from recostar.controle.fonctions_communes.chargement import charger_features, nom_couche, parcourir_couches


def _ecrire_couche(repertoire: Path, nom: str, features: list[dict[str, Any]], crs: Any = None) -> None:
    """Ecrit une couche GeoJSON de test."""
    collection: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        collection["crs"] = crs
    (repertoire / nom).write_text(json.dumps(collection), encoding="utf-8")


def _feature(identifiant: str) -> dict[str, Any]:
    return {"type": "Feature", "properties": {"id": identifiant}, "geometry": None}


class TestNomCouche:
    """Derivation du nom de couche depuis le nom de fichier."""

    def test_extension_retiree(self) -> None:
        assert nom_couche("RPD_Terre_Reco.geojson") == "RPD_Terre_Reco"

    def test_extension_majuscules(self) -> None:
        assert nom_couche("RPD_Terre_Reco.GEOJSON") == "RPD_Terre_Reco"

    def test_sans_extension_inchange(self) -> None:
        assert nom_couche("RPD_Terre_Reco") == "RPD_Terre_Reco"


class TestChargerFeatures:
    """Chargement d'une couche nommee."""

    def test_couche_absente_signalee(self, tmp_path: Path) -> None:
        """Le troisieme membre distingue l'absence : les controles la signalent."""
        features, crs, absent = charger_features(str(tmp_path), "RPD_Jonction_Reco.geojson")
        assert (features, crs, absent) == ([], None, True)

    def test_couche_vide_n_est_pas_absente(self, tmp_path: Path) -> None:
        """Une couche vide est une donnee valide, pas une donnee manquante."""
        _ecrire_couche(tmp_path, "RPD_Jonction_Reco.geojson", [])
        features, _, absent = charger_features(str(tmp_path), "RPD_Jonction_Reco.geojson")
        assert features == []
        assert absent is False

    def test_features_retournees(self, tmp_path: Path) -> None:
        _ecrire_couche(tmp_path, "RPD_Jonction_Reco.geojson", [_feature("j1"), _feature("j2")])
        features, _, absent = charger_features(str(tmp_path), "RPD_Jonction_Reco.geojson")
        assert [f["properties"]["id"] for f in features] == ["j1", "j2"]
        assert absent is False

    def test_crs_restitue(self, tmp_path: Path) -> None:
        """Le CRS est propage tel quel dans les fichiers d'ecarts produits."""
        crs = {"type": "name", "properties": {"name": "EPSG:2154"}}
        _ecrire_couche(tmp_path, "RPD_Jonction_Reco.geojson", [_feature("j1")], crs)
        _, crs_lu, _ = charger_features(str(tmp_path), "RPD_Jonction_Reco.geojson")
        assert crs_lu == crs

    def test_fichier_illisible_leve(self, tmp_path: Path) -> None:
        """Un JSON invalide leve : la couche existe mais son contenu est faux.

        Le silence serait pire que l'erreur — un jeu corrompu serait declare
        conforme faute d'anomalie detectee. L'echec est rattrape par
        l'orchestrateur, qui reporte la famille comme non executee.
        """
        (tmp_path / "RPD_Jonction_Reco.geojson").write_text("{ ceci n'est pas du JSON", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            charger_features(str(tmp_path), "RPD_Jonction_Reco.geojson")


class TestParcourirCouches:
    """Parcours generateur des couches d'un repertoire."""

    def test_repertoire_vide(self, tmp_path: Path) -> None:
        assert list(parcourir_couches(str(tmp_path))) == []

    def test_couches_nommees_sans_extension(self, tmp_path: Path) -> None:
        _ecrire_couche(tmp_path, "RPD_Terre_Reco.geojson", [_feature("t1")])
        _ecrire_couche(tmp_path, "RPD_JeuBarres_Reco.geojson", [])
        couches = dict(parcourir_couches(str(tmp_path)))
        assert set(couches) == {"RPD_Terre_Reco", "RPD_JeuBarres_Reco"}

    def test_fichiers_d_ecarts_exclus(self, tmp_path: Path) -> None:
        """Relire ses propres sorties ferait compter deux fois les anomalies."""
        _ecrire_couche(tmp_path, "RPD_Terre_Reco.geojson", [_feature("t1")])
        _ecrire_couche(tmp_path, "ecarts_e0604_noeuds.geojson", [_feature("a1")])
        assert [couche for couche, _ in parcourir_couches(str(tmp_path))] == ["RPD_Terre_Reco"]

    def test_couche_illisible_leve(self, tmp_path: Path) -> None:
        """Une couche corrompue interrompt le parcours, comme le chargement
        nomme : le parcours ne masque pas ce que `charger_features` signale."""
        _ecrire_couche(tmp_path, "RPD_Terre_Reco.geojson", [_feature("t1")])
        (tmp_path / "RPD_JeuBarres_Reco.geojson").write_text("<<invalide>>", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            list(parcourir_couches(str(tmp_path)))

    def test_generateur_paresseux(self, tmp_path: Path) -> None:
        """Le parcours ne doit pas detenir toutes les couches a la fois : le
        volume du jeu est sans rapport avec le nombre d'anomalies cherchees."""
        for indice in range(3):
            _ecrire_couche(tmp_path, f"RPD_Couche{indice}_Reco.geojson", [_feature(f"e{indice}")])
        parcours = parcourir_couches(str(tmp_path))
        premiere = next(parcours)
        assert isinstance(premiere, tuple)
        assert len(list(parcours)) == 2
