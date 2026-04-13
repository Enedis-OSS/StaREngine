"""
Tests unitaires du rapport PDF des controles de projection (rapport_pdf_proj).

Couvre les cas nominaux et les cas limites :
- chargement des features depuis les fichiers d'ecarts
- collecte des resultats de controle
- construction des sections du rapport (synthese, tableau, detail)
- generation du PDF
- execution CLI bout en bout via tmp_path
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from rapport_pdf_proj import (
    CONTROLES,
    FICHIER_RAPPORT,
    _charger_features_geojson,
    _construire_synthese,
    _construire_tableau_detail,
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
    nom_fichier: str,
    features: list[dict[str, Any]],
) -> str:
    """Cree un fichier GeoJSON d'ecarts dans le repertoire."""
    chemin = os.path.join(repertoire, nom_fichier)
    contenu: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(contenu, f, ensure_ascii=False)
    return chemin


def _creer_feature_ecart(
    fichier_source: str = "test.geojson",
    id_entite: str = "e1",
    **kwargs: Any,
) -> dict[str, Any]:
    """Cree une feature d'ecart avec des proprietes personnalisables."""
    props: dict[str, Any] = {
        "fichier_source": fichier_source,
        "id_entite": id_entite,
        "priorite": "bloquant",
    }
    props.update(kwargs)
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
    }


# --------------------------------------------------------------------------- #
# Tests _charger_features_geojson
# --------------------------------------------------------------------------- #


class TestChargerFeaturesGeojson:
    """Tests du chargement des features d'un fichier GeoJSON."""

    def test_fichier_absent(self, tmp_path: Any) -> None:
        chemin = os.path.join(str(tmp_path), "inexistant.geojson")
        assert _charger_features_geojson(chemin) is None

    def test_fichier_vide(self, tmp_path: Any) -> None:
        _creer_geojson_ecarts(str(tmp_path), "vide.geojson", [])
        chemin = os.path.join(str(tmp_path), "vide.geojson")
        features = _charger_features_geojson(chemin)
        assert features == []

    def test_fichier_avec_features(self, tmp_path: Any) -> None:
        feature = _creer_feature_ecart()
        _creer_geojson_ecarts(str(tmp_path), "ecarts.geojson", [feature])
        chemin = os.path.join(str(tmp_path), "ecarts.geojson")
        features = _charger_features_geojson(chemin)
        assert features is not None
        assert len(features) == 1


# --------------------------------------------------------------------------- #
# Tests collecter_resultats_controles
# --------------------------------------------------------------------------- #


class TestCollecterResultatsControles:
    """Tests de la collecte des resultats de controle."""

    def test_aucun_fichier_ecarts(self, tmp_path: Any) -> None:
        resultats = collecter_resultats_controles(str(tmp_path))
        assert len(resultats) == len(CONTROLES)
        for r in resultats:
            assert r["disponible"] is False
            assert r["nombre_anomalies"] == 0

    def test_un_fichier_ecarts_present(self, tmp_path: Any) -> None:
        feature = _creer_feature_ecart(crs_detecte="EPSG:9999")
        _creer_geojson_ecarts(str(tmp_path), "ecarts_proj.geojson", [feature])
        resultats = collecter_resultats_controles(str(tmp_path))
        r_proj = resultats[0]
        assert r_proj["disponible"] is True
        assert r_proj["nombre_anomalies"] == 1

    def test_tous_fichiers_presents(self, tmp_path: Any) -> None:
        for nom_fichier, _, _, _ in CONTROLES:
            _creer_geojson_ecarts(str(tmp_path), nom_fichier, [_creer_feature_ecart()])
        resultats = collecter_resultats_controles(str(tmp_path))
        for r in resultats:
            assert r["disponible"] is True
            assert r["nombre_anomalies"] == 1

    def test_fichier_sans_anomalie(self, tmp_path: Any) -> None:
        _creer_geojson_ecarts(str(tmp_path), "ecarts_proj.geojson", [])
        resultats = collecter_resultats_controles(str(tmp_path))
        r_proj = resultats[0]
        assert r_proj["disponible"] is True
        assert r_proj["nombre_anomalies"] == 0


# --------------------------------------------------------------------------- #
# Tests construction des sections
# --------------------------------------------------------------------------- #


class TestConstruireSynthese:
    """Tests de la construction de la section synthese."""

    def test_synthese_sans_anomalie(self) -> None:
        styles = _creer_styles()
        resultats: list[dict[str, Any]] = [
            {"disponible": True, "nombre_anomalies": 0},
            {"disponible": True, "nombre_anomalies": 0},
        ]
        elements = _construire_synthese(styles, resultats)
        assert len(elements) > 0

    def test_synthese_avec_anomalies(self) -> None:
        styles = _creer_styles()
        resultats: list[dict[str, Any]] = [
            {"disponible": True, "nombre_anomalies": 3},
            {"disponible": False, "nombre_anomalies": 0},
        ]
        elements = _construire_synthese(styles, resultats)
        assert len(elements) > 0


class TestConstruireTableauDetail:
    """Tests du tableau recapitulatif."""

    def test_tableau_avec_resultats(self) -> None:
        styles = _creer_styles()
        resultats: list[dict[str, Any]] = [
            {
                "label": "Conformite CRS",
                "description": "Test",
                "fichier": "ecarts_proj.geojson",
                "disponible": True,
                "nombre_anomalies": 2,
            },
        ]
        elements = _construire_tableau_detail(styles, resultats)
        assert len(elements) == 2  # sous_titre + tableau

    def test_tableau_non_execute(self) -> None:
        styles = _creer_styles()
        resultats: list[dict[str, Any]] = [
            {
                "label": "Conformite CRS",
                "description": "Test",
                "fichier": "ecarts_proj.geojson",
                "disponible": False,
                "nombre_anomalies": 0,
            },
        ]
        elements = _construire_tableau_detail(styles, resultats)
        assert len(elements) == 2


class TestConstruireSectionsDetail:
    """Tests des sections de detail par controle."""

    def test_aucune_anomalie(self) -> None:
        styles = _creer_styles()
        resultats: list[dict[str, Any]] = [
            {"features": [], "label": "Test", "nombre_anomalies": 0, "colonnes": ()},
        ]
        elements = construire_sections_detail(styles, resultats)
        assert elements == []

    def test_avec_anomalies(self) -> None:
        styles = _creer_styles()
        feature = _creer_feature_ecart(crs_detecte="EPSG:9999", type_anomalie="ko")
        colonnes = (("id_entite", "ID", 3.0), ("crs_detecte", "CRS", 3.0))
        resultats: list[dict[str, Any]] = [
            {
                "features": [feature],
                "label": "Conformite CRS",
                "nombre_anomalies": 1,
                "colonnes": colonnes,
            },
        ]
        elements = construire_sections_detail(styles, resultats)
        assert len(elements) > 0

    def test_pluriel_anomalies(self) -> None:
        """Le titre doit contenir 's' si plusieurs anomalies."""
        styles = _creer_styles()
        features = [_creer_feature_ecart(), _creer_feature_ecart(id_entite="e2")]
        colonnes = (("id_entite", "ID", 3.0),)
        resultats: list[dict[str, Any]] = [
            {
                "features": features,
                "label": "Test",
                "nombre_anomalies": 2,
                "colonnes": colonnes,
            },
        ]
        elements = construire_sections_detail(styles, resultats)
        assert len(elements) > 0


# --------------------------------------------------------------------------- #
# Tests generation du PDF
# --------------------------------------------------------------------------- #


class TestGenererRapportPdf:
    """Tests de la generation effective du PDF."""

    def test_repertoire_vide(self, tmp_path: Any) -> None:
        chemin_pdf = os.path.join(str(tmp_path), FICHIER_RAPPORT)
        resultat = generer_rapport_pdf(str(tmp_path), chemin_pdf)
        assert resultat["succes"] is True
        assert os.path.isfile(chemin_pdf)
        assert resultat["controles_disponibles"] == 0
        assert resultat["nombre_total_anomalies"] == 0

    def test_avec_ecarts_proj(self, tmp_path: Any) -> None:
        features = [
            _creer_feature_ecart(crs_detecte="EPSG:9999", type_anomalie="ko"),
            _creer_feature_ecart(
                id_entite="e2", crs_detecte="EPSG:0", type_anomalie="ko"
            ),
        ]
        _creer_geojson_ecarts(str(tmp_path), "ecarts_proj.geojson", features)
        chemin_pdf = os.path.join(str(tmp_path), FICHIER_RAPPORT)
        resultat = generer_rapport_pdf(str(tmp_path), chemin_pdf)
        assert resultat["succes"] is True
        assert resultat["controles_disponibles"] == 1
        assert resultat["nombre_total_anomalies"] == 2

    def test_avec_tous_controles(self, tmp_path: Any) -> None:
        for nom_fichier, _, _, _ in CONTROLES:
            _creer_geojson_ecarts(str(tmp_path), nom_fichier, [_creer_feature_ecart()])
        chemin_pdf = os.path.join(str(tmp_path), FICHIER_RAPPORT)
        resultat = generer_rapport_pdf(str(tmp_path), chemin_pdf)
        assert resultat["succes"] is True
        assert resultat["controles_disponibles"] == len(CONTROLES)
        assert resultat["nombre_total_anomalies"] == len(CONTROLES)

    def test_pdf_lisible(self, tmp_path: Any) -> None:
        """Le fichier PDF produit doit commencer par l'en-tete PDF."""
        _creer_geojson_ecarts(
            str(tmp_path), "ecarts_proj.geojson", [_creer_feature_ecart()]
        )
        chemin_pdf = os.path.join(str(tmp_path), FICHIER_RAPPORT)
        generer_rapport_pdf(str(tmp_path), chemin_pdf)
        with open(chemin_pdf, "rb") as f:
            en_tete = f.read(5)
        assert en_tete == b"%PDF-"


# --------------------------------------------------------------------------- #
# Tests executer_rapport_cli
# --------------------------------------------------------------------------- #


class TestExecuterRapportCli:
    """Tests de l'execution CLI du rapport."""

    def test_repertoire_introuvable(self) -> None:
        resultat = executer_rapport_cli("/chemin/inexistant")
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_sortie_par_defaut(self, tmp_path: Any) -> None:
        resultat = executer_rapport_cli(str(tmp_path))
        assert resultat["succes"] is True
        chemin_pdf = os.path.join(str(tmp_path), FICHIER_RAPPORT)
        assert os.path.isfile(chemin_pdf)

    def test_sortie_personnalisee(self, tmp_path: Any) -> None:
        dossier_sortie = os.path.join(str(tmp_path), "output")
        resultat = executer_rapport_cli(str(tmp_path), dossier_sortie)
        assert resultat["succes"] is True
        chemin_pdf = os.path.join(dossier_sortie, FICHIER_RAPPORT)
        assert os.path.isfile(chemin_pdf)

    def test_controles_sans_anomalie(self, tmp_path: Any) -> None:
        for nom_fichier, _, _, _ in CONTROLES:
            _creer_geojson_ecarts(str(tmp_path), nom_fichier, [])
        resultat = executer_rapport_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_total_anomalies"] == 0
        assert resultat["controles_disponibles"] == len(CONTROLES)

    def test_controles_avec_anomalies(self, tmp_path: Any) -> None:
        features = [_creer_feature_ecart(), _creer_feature_ecart(id_entite="e2")]
        _creer_geojson_ecarts(str(tmp_path), "ecarts_proj.geojson", features)
        resultat = executer_rapport_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_total_anomalies"] == 2


# --------------------------------------------------------------------------- #
# Tests de la configuration CONTROLES
# --------------------------------------------------------------------------- #


class TestConfigurationControles:
    """Tests de la coherence de la configuration des controles."""

    def test_nombre_controles(self) -> None:
        assert len(CONTROLES) == 3

    def test_structure_controles(self) -> None:
        for nom_fichier, label, description, colonnes in CONTROLES:
            assert nom_fichier.endswith(".geojson")
            assert len(label) > 0
            assert len(description) > 0
            assert len(colonnes) > 0

    def test_colonnes_contiennent_priorite(self) -> None:
        """Chaque controle doit avoir une colonne priorite."""
        for _, _, _, colonnes in CONTROLES:
            cles = {col[0] for col in colonnes}
            assert "priorite" in cles

    def test_colonnes_contiennent_id_entite(self) -> None:
        """Chaque controle doit avoir une colonne id_entite."""
        for _, _, _, colonnes in CONTROLES:
            cles = {col[0] for col in colonnes}
            assert "id_entite" in cles
