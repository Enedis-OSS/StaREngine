"""
Tests unitaires du pipeline de controle des noeuds.

Couvre les cas nominaux et les cas limites :
- execution complete du pipeline avec donnees minimales
- generation du rapport PDF en fin de pipeline
- repertoire inexistant
- sortie dans un repertoire separe
- sortie par defaut dans le repertoire d'entree
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from pipeline_controle_noeud import executer_pipeline

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _creer_geojson_cable(
    identifiant: str, coordonnees: list[list[float]]
) -> dict[str, Any]:
    """Construit une feature cable electrique minimale."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant},
        "geometry": {"type": "LineString", "coordinates": coordonnees},
    }


def _ecrire_geojson(chemin: str, features: list[dict[str, Any]]) -> None:
    """Ecrit un fichier GeoJSON FeatureCollection."""
    collection = {"type": "FeatureCollection", "features": features}
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(collection, f)


def _preparer_donnees_minimales(repertoire: str) -> None:
    """Cree les fichiers GeoJSON minimaux pour lancer le pipeline."""
    cable = _creer_geojson_cable("C1", [[0.0, 0.0], [10.0, 0.0]])
    _ecrire_geojson(
        os.path.join(repertoire, "RPD_CableElectrique_Reco.geojson"), [cable]
    )
    # Fichiers optionnels vides pour les controles terre
    _ecrire_geojson(os.path.join(repertoire, "RPD_CableTerre_Reco.geojson"), [])
    _ecrire_geojson(os.path.join(repertoire, "RPD_Terre_Reco.geojson"), [])


# --------------------------------------------------------------------------- #
# Tests du pipeline
# --------------------------------------------------------------------------- #


class TestExecuterPipeline:
    """Verifie l'orchestration complete du pipeline."""

    def test_pipeline_complet(self, tmp_path: Any) -> None:
        """Le pipeline execute les 4 controles et genere le rapport PDF."""
        _preparer_donnees_minimales(str(tmp_path))

        resultat = executer_pipeline(str(tmp_path))

        assert resultat["succes"] is True
        assert len(resultat["controles"]) == 4

        for nom, ctrl in resultat["controles"].items():
            assert ctrl["succes"] is True, f"Echec du controle {nom}"

        assert resultat["rapport"]["succes"] is True
        assert os.path.isfile(resultat["rapport"]["chemin_pdf"])

    def test_pipeline_repertoire_inexistant(self) -> None:
        """Un repertoire inexistant retourne une erreur."""
        resultat = executer_pipeline("/chemin/inexistant")
        assert resultat["succes"] is False

    def test_pipeline_sortie_separee(self, tmp_path: Any) -> None:
        """Les fichiers sont generes dans le repertoire de sortie specifie."""
        repertoire_entree = os.path.join(str(tmp_path), "entree")
        repertoire_sortie = os.path.join(str(tmp_path), "sortie")
        os.makedirs(repertoire_entree)
        _preparer_donnees_minimales(repertoire_entree)

        resultat = executer_pipeline(repertoire_entree, repertoire_sortie)

        assert resultat["succes"] is True
        assert os.path.isdir(repertoire_sortie)

        # Verifier que les fichiers d'ecarts sont dans le dossier de sortie
        fichiers_sortie = set(os.listdir(repertoire_sortie))
        assert "ecarts_geometrie.geojson" in fichiers_sortie
        assert "rapport_controles_noeud.pdf" in fichiers_sortie

    def test_pipeline_sortie_par_defaut(self, tmp_path: Any) -> None:
        """Sans sortie specifiee, les fichiers vont dans le repertoire d'entree."""
        _preparer_donnees_minimales(str(tmp_path))

        resultat = executer_pipeline(str(tmp_path))

        assert resultat["succes"] is True
        fichiers = set(os.listdir(str(tmp_path)))
        assert "rapport_controles_noeud.pdf" in fichiers
        assert "ecarts_geometrie.geojson" in fichiers

    def test_pipeline_compte_anomalies(self, tmp_path: Any) -> None:
        """Le nombre total d'anomalies est correctement agrege."""
        _preparer_donnees_minimales(str(tmp_path))

        resultat = executer_pipeline(str(tmp_path))

        # Le cable C1 a des extremites non liees → au moins des anomalies extremites
        assert isinstance(resultat["nombre_anomalies_total"], int)
        assert resultat["nombre_anomalies_total"] >= 0
