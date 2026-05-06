"""Tests du script rapport_pdf_gml.py."""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from rapport_pdf_gml import (
    CONTROLES,
    FICHIER_RAPPORT,
    _charger_features_geojson,
    _construire_synthese,
    _construire_tableau_detail,
    _construire_tableau_entites,
    _creer_styles,
    collecter_resultats_controles,
    construire_sections_detail,
    executer_rapport_cli,
    generer_rapport_pdf,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _creer_geojson_ecarts(
    repertoire: str,
    nom: str,
    nb_features: int,
    proprietes_extra: dict[str, Any] | None = None,
) -> str:
    """Cree un fichier GeoJSON d'ecarts avec le nombre de features donne."""
    props_base: dict[str, Any] = {
        "id_duplique": "id0",
        "fichier_source": "RPD_Test.geojson",
        "type_anomalie": "id_duplique",
        "message": "Doublon detecte",
        "priorite": "bloquant",
    }
    if proprietes_extra:
        props_base.update(proprietes_extra)

    features = [
        {
            "type": "Feature",
            "properties": {**props_base, "id_duplique": f"id{i}"},
            "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
        }
        for i in range(nb_features)
    ]
    chemin = os.path.join(repertoire, nom)
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump({"type": "FeatureCollection", "features": features}, fichier)
    return chemin


def _creer_geojson_unicite(repertoire: str, nb: int) -> str:
    """Cree un fichier d'ecarts d'unicite realiste."""
    return _creer_geojson_ecarts(
        repertoire,
        "ecarts_unicite_id.geojson",
        nb,
    )


def _creer_geojson_valeur_xsd(repertoire: str, nb: int) -> str:
    """Cree un fichier d'ecarts de valeur XSD realiste."""
    return _creer_geojson_ecarts(
        repertoire,
        "ecarts_valeur_xsd.geojson",
        nb,
        proprietes_extra={
            "id_entite": "entite_0",
            "fichier_source": "RPD_Jonction_Reco.geojson",
            "type_anomalie": "valeur_non_conforme_xsd",
            "message": "DomaineTension='HTZ' (attendu : DomaineTensionValue)",
            "priorite": "bloquant",
        },
    )


# --------------------------------------------------------------------------- #
# Tests de _charger_features_geojson
# --------------------------------------------------------------------------- #


class TestChargerFeatures:
    """Tests du chargement des features d'un fichier d'ecarts."""

    def test_fichier_absent(self, tmp_path: Any) -> None:
        chemin = os.path.join(str(tmp_path), "inexistant.geojson")
        assert _charger_features_geojson(chemin) is None

    def test_fichier_vide(self, tmp_path: Any) -> None:
        chemin = _creer_geojson_ecarts(str(tmp_path), "ecarts.geojson", 0)
        features = _charger_features_geojson(chemin)
        assert features is not None
        assert len(features) == 0

    def test_fichier_avec_features(self, tmp_path: Any) -> None:
        chemin = _creer_geojson_ecarts(str(tmp_path), "ecarts.geojson", 5)
        features = _charger_features_geojson(chemin)
        assert features is not None
        assert len(features) == 5

    def test_proprietes_chargees(self, tmp_path: Any) -> None:
        chemin = _creer_geojson_unicite(str(tmp_path), 1)
        features = _charger_features_geojson(chemin)
        assert features is not None
        props = features[0]["properties"]
        assert "id_duplique" in props
        assert "fichier_source" in props


# --------------------------------------------------------------------------- #
# Tests de collecter_resultats_controles
# --------------------------------------------------------------------------- #


class TestCollecterResultats:
    """Tests de la collecte des resultats de controles."""

    def test_aucun_fichier(self, tmp_path: Any) -> None:
        resultats = collecter_resultats_controles(str(tmp_path))
        assert len(resultats) == len(CONTROLES)
        for r in resultats:
            assert r["disponible"] is False
            assert r["nombre_anomalies"] == 0
            assert r["features"] == []

    def test_tous_les_fichiers(self, tmp_path: Any) -> None:
        rep = str(tmp_path)
        for nom_fichier, _, _, _ in CONTROLES:
            _creer_geojson_ecarts(rep, nom_fichier, 3)

        resultats = collecter_resultats_controles(rep)
        for r in resultats:
            assert r["disponible"] is True
            assert r["nombre_anomalies"] == 3
            assert len(r["features"]) == 3

    def test_colonnes_presentes(self, tmp_path: Any) -> None:
        resultats = collecter_resultats_controles(str(tmp_path))
        for r in resultats:
            assert "colonnes" in r
            assert len(r["colonnes"]) > 0


# --------------------------------------------------------------------------- #
# Tests des fonctions de construction du rapport
# --------------------------------------------------------------------------- #


class TestConstructionRapport:
    """Tests des fonctions de construction des elements du rapport."""

    def test_creer_styles(self) -> None:
        styles = _creer_styles()
        assert "titre" in styles
        assert "sous_titre" in styles
        assert "normal" in styles
        assert "cellule" in styles

    def test_construire_synthese(self) -> None:
        styles = _creer_styles()
        resultats = [
            {"label": "A", "disponible": True, "nombre_anomalies": 3},
            {"label": "B", "disponible": False, "nombre_anomalies": 0},
        ]
        elements = _construire_synthese(styles, resultats)
        assert len(elements) > 0

    def test_construire_tableau_detail(self) -> None:
        styles = _creer_styles()
        resultats = [
            {
                "label": "Test",
                "description": "Description",
                "fichier": "ecarts.geojson",
                "nombre_anomalies": 2,
                "disponible": True,
            },
        ]
        elements = _construire_tableau_detail(styles, resultats)
        assert len(elements) > 0


# --------------------------------------------------------------------------- #
# Tests du detail des entites
# --------------------------------------------------------------------------- #


class TestDetailEntites:
    """Tests de la construction des sections de detail par entite."""

    def test_tableau_entites_vide(self) -> None:
        styles = _creer_styles()
        colonnes = (("id_duplique", "ID", 3.0),)
        tableau = _construire_tableau_entites(styles["cellule"], [], colonnes)
        assert tableau is not None

    def test_tableau_entites_avec_features(self) -> None:
        styles = _creer_styles()
        colonnes = (
            ("id_duplique", "ID duplique", 4.0),
            ("priorite", "Priorite", 2.0),
        )
        features = [
            {"properties": {"id_duplique": "id1", "priorite": "bloquant"}},
            {"properties": {"id_duplique": "id2", "priorite": "bloquant"}},
        ]
        tableau = _construire_tableau_entites(styles["cellule"], features, colonnes)
        assert tableau is not None

    def test_tableau_entites_propriete_manquante(self) -> None:
        """Une propriete absente affiche '-' sans erreur."""
        styles = _creer_styles()
        colonnes = (("champ_inexistant", "Champ", 3.0),)
        features = [{"properties": {"id_duplique": "id1"}}]
        tableau = _construire_tableau_entites(styles["cellule"], features, colonnes)
        assert tableau is not None

    def test_sections_detail_sans_anomalies(self) -> None:
        styles = _creer_styles()
        resultats = [
            {"label": "Test", "features": [], "nombre_anomalies": 0, "colonnes": ()},
        ]
        elements = construire_sections_detail(styles, resultats)
        assert len(elements) == 0

    def test_sections_detail_avec_anomalies(self) -> None:
        styles = _creer_styles()
        resultats = [
            {
                "label": "Unicite ID",
                "features": [
                    {
                        "properties": {
                            "id_duplique": "id1",
                            "fichier_source": "f.geojson",
                        }
                    },
                ],
                "nombre_anomalies": 1,
                "colonnes": (("id_duplique", "ID", 3.0),),
            },
        ]
        elements = construire_sections_detail(styles, resultats)
        assert len(elements) >= 2

    def test_sections_detail_pluriel(self) -> None:
        """Le titre doit etre au pluriel si plusieurs anomalies."""
        styles = _creer_styles()
        resultats = [
            {
                "label": "Test",
                "features": [{"properties": {}}, {"properties": {}}],
                "nombre_anomalies": 2,
                "colonnes": (("id_duplique", "ID", 3.0),),
            },
        ]
        elements = construire_sections_detail(styles, resultats)
        assert len(elements) >= 2

    def test_sections_detail_singulier(self) -> None:
        """Le titre doit etre au singulier si une seule anomalie."""
        styles = _creer_styles()
        resultats = [
            {
                "label": "Test",
                "features": [{"properties": {}}],
                "nombre_anomalies": 1,
                "colonnes": (("id_duplique", "ID", 3.0),),
            },
        ]
        elements = construire_sections_detail(styles, resultats)
        assert len(elements) >= 2


# --------------------------------------------------------------------------- #
# Tests de la generation du PDF
# --------------------------------------------------------------------------- #


class TestGenerationPdf:
    """Tests de la generation effective du fichier PDF."""

    def test_generer_rapport_vide(self, tmp_path: Any) -> None:
        rep = str(tmp_path)
        chemin_pdf = os.path.join(rep, FICHIER_RAPPORT)

        resultat = generer_rapport_pdf(rep, chemin_pdf)

        assert resultat["succes"] is True
        assert os.path.isfile(chemin_pdf)
        assert resultat["controles_disponibles"] == 0
        assert resultat["nombre_total_anomalies"] == 0

    def test_generer_rapport_avec_ecarts(self, tmp_path: Any) -> None:
        rep = str(tmp_path)
        _creer_geojson_unicite(rep, 4)
        chemin_pdf = os.path.join(rep, FICHIER_RAPPORT)

        resultat = generer_rapport_pdf(rep, chemin_pdf)

        assert resultat["succes"] is True
        assert os.path.isfile(chemin_pdf)
        assert resultat["controles_disponibles"] == 1
        assert resultat["nombre_total_anomalies"] == 4

    def test_generer_rapport_avec_deux_controles(self, tmp_path: Any) -> None:
        """Le PDF avec les deux types d'ecarts detecte les deux controles."""
        rep = str(tmp_path)
        _creer_geojson_unicite(rep, 2)
        _creer_geojson_valeur_xsd(rep, 3)
        chemin_pdf = os.path.join(rep, FICHIER_RAPPORT)

        resultat = generer_rapport_pdf(rep, chemin_pdf)

        assert resultat["succes"] is True
        assert resultat["controles_disponibles"] == 2
        assert resultat["nombre_total_anomalies"] == 5

    def test_pdf_non_vide(self, tmp_path: Any) -> None:
        rep = str(tmp_path)
        _creer_geojson_unicite(rep, 1)
        chemin_pdf = os.path.join(rep, FICHIER_RAPPORT)

        generer_rapport_pdf(rep, chemin_pdf)

        taille = os.path.getsize(chemin_pdf)
        assert taille > 0

    def test_pdf_avec_detail_entites(self, tmp_path: Any) -> None:
        """Le PDF avec des anomalies doit etre plus volumineux (sections detail)."""
        rep = str(tmp_path)
        _creer_geojson_unicite(rep, 5)
        chemin_pdf = os.path.join(rep, FICHIER_RAPPORT)

        generer_rapport_pdf(rep, chemin_pdf)

        taille = os.path.getsize(chemin_pdf)
        assert taille > 2000


# --------------------------------------------------------------------------- #
# Tests du CLI
# --------------------------------------------------------------------------- #


class TestCli:
    """Tests de l'interface en ligne de commande."""

    def test_repertoire_inexistant(self) -> None:
        resultat = executer_rapport_cli("/chemin/inexistant")
        assert resultat["succes"] is False

    def test_sortie_par_defaut(self, tmp_path: Any) -> None:
        rep = str(tmp_path)
        resultat = executer_rapport_cli(rep)

        assert resultat["succes"] is True
        chemin_pdf = os.path.join(rep, FICHIER_RAPPORT)
        assert os.path.isfile(chemin_pdf)

    def test_sortie_personnalisee(self, tmp_path: Any) -> None:
        rep = str(tmp_path)
        sortie = os.path.join(rep, "resultats")

        resultat = executer_rapport_cli(rep, sortie)

        assert resultat["succes"] is True
        chemin_pdf = os.path.join(sortie, FICHIER_RAPPORT)
        assert os.path.isfile(chemin_pdf)

    def test_contenu_resultat(self, tmp_path: Any) -> None:
        rep = str(tmp_path)
        _creer_geojson_unicite(rep, 4)

        resultat = executer_rapport_cli(rep)

        assert resultat["succes"] is True
        assert resultat["controles_disponibles"] == 1
        assert resultat["nombre_total_anomalies"] == 4
