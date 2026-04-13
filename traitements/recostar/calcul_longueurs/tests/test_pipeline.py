"""Tests du pipeline unifie de calcul et rapport des longueurs de cables."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import (  # type: ignore[import-not-found]
    ResultatPipeline,
    _valider_repertoire_entree,
    executer_pipeline,
)

# --- Fixtures ---


@pytest.fixture
def dossier_geojson(tmp_path):
    """Cree un dossier temporaire avec des fichiers GeoJSON de test."""
    cable = {
        "type": "Feature",
        "properties": {
            "id": "cable_pipe_1",
            "DomaineTension": "BT",
            "Isolant": "Reticulee",
            "HierarchieBT": "Reseau",
        },
        "geometry": {
            "type": "LineString",
            "coordinates": [[0.0, 0.0], [100.0, 0.0]],
        },
    }
    cable_hta = {
        "type": "Feature",
        "properties": {
            "id": "cable_pipe_2",
            "DomaineTension": "HTA",
            "Isolant": "Nu",
        },
        "geometry": {
            "type": "LineString",
            "coordinates": [[200.0, 0.0], [300.0, 0.0]],
        },
    }

    _ecrire_geojson(tmp_path, "RPD_CableElectrique_Reco.geojson", [cable, cable_hta])
    return tmp_path


@pytest.fixture
def dossier_geojson_avec_aerien(dossier_geojson):
    """Dossier GeoJSON avec un cheminement aerien."""
    aerien = {
        "type": "Feature",
        "properties": {"id": "aer_1", "cables_href": "cable_pipe_1"},
        "geometry": {"type": "LineString", "coordinates": [[0, 0], [100, 0]]},
    }
    _ecrire_geojson(dossier_geojson, "RPD_Aerien_Reco.geojson", [aerien])
    return dossier_geojson


def _ecrire_geojson(dossier, nom_fichier, features):
    """Ecrit un fichier GeoJSON dans le dossier specifie."""
    collection = {"type": "FeatureCollection", "features": features}
    chemin = os.path.join(str(dossier), nom_fichier)
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(collection, fichier, ensure_ascii=False)


# --- Tests de ResultatPipeline ---


class TestResultatPipeline:
    """Tests de la classe ResultatPipeline."""

    def test_etat_initial(self):
        """Etat initial : succes a False, champs vides."""
        resultat = ResultatPipeline()
        assert resultat.succes is False
        assert resultat.erreur == ""
        assert resultat.chemin_json == ""
        assert resultat.chemin_pdf == ""
        assert resultat.nb_cables == 0

    def test_vers_dict_succes(self):
        """Conversion en dict avec succes."""
        resultat = ResultatPipeline()
        resultat.succes = True
        resultat.chemin_json = "/chemin/json"
        resultat.chemin_pdf = "/chemin/pdf"
        resultat.nb_cables = 5

        d = resultat.vers_dict()
        assert d["succes"] is True
        assert d["chemin_json"] == "/chemin/json"
        assert d["chemin_pdf"] == "/chemin/pdf"
        assert d["nb_cables"] == 5
        assert "erreur" not in d

    def test_vers_dict_erreur(self):
        """Conversion en dict avec erreur."""
        resultat = ResultatPipeline()
        resultat.erreur = "Fichier introuvable"

        d = resultat.vers_dict()
        assert d["succes"] is False
        assert d["erreur"] == "Fichier introuvable"


# --- Tests de _valider_repertoire_entree ---


class TestValiderRepertoireEntree:
    """Tests de la validation du repertoire d'entree."""

    def test_repertoire_existant(self, tmp_path):
        """Repertoire existant : retourne None."""
        assert _valider_repertoire_entree(str(tmp_path)) is None

    def test_repertoire_inexistant(self):
        """Repertoire inexistant : retourne un message d'erreur."""
        erreur = _valider_repertoire_entree("/chemin/inexistant/xyz")
        assert erreur is not None
        assert "introuvable" in erreur


# --- Tests de executer_pipeline ---


class TestExecuterPipeline:
    """Tests du pipeline complet."""

    def test_repertoire_entree_inexistant(self):
        """Repertoire d'entree inexistant : retourne erreur."""
        resultat = executer_pipeline("/chemin/inexistant/xyz")
        assert resultat.succes is False
        assert "introuvable" in resultat.erreur

    def test_fichier_cables_absent(self, tmp_path):
        """Dossier vide sans fichier cables : retourne erreur."""
        resultat = executer_pipeline(str(tmp_path))
        assert resultat.succes is False
        assert "introuvable" in resultat.erreur

    def test_pipeline_nominal(self, dossier_geojson):
        """Execution nominale : produit JSON et PDF."""
        resultat = executer_pipeline(str(dossier_geojson))

        assert resultat.succes is True
        assert resultat.nb_cables == 2
        assert os.path.isfile(resultat.chemin_json)
        assert os.path.isfile(resultat.chemin_pdf)
        assert resultat.chemin_json.endswith(".json")
        assert resultat.chemin_pdf.endswith(".pdf")

    def test_pipeline_sortie_dans_entree(self, dossier_geojson):
        """Sans repertoire de sortie : fichiers dans le dossier d'entree."""
        resultat = executer_pipeline(str(dossier_geojson))

        assert resultat.succes is True
        dossier_rapport = os.path.join(str(dossier_geojson), "rapport")
        assert os.path.isdir(dossier_rapport)
        assert resultat.chemin_json.startswith(dossier_rapport)
        assert resultat.chemin_pdf.startswith(dossier_rapport)

    def test_pipeline_sortie_personnalisee(self, dossier_geojson, tmp_path):
        """Repertoire de sortie personnalise : fichiers dans ce repertoire."""
        dossier_sortie = tmp_path / "sortie_custom"
        dossier_sortie.mkdir()

        resultat = executer_pipeline(str(dossier_geojson), str(dossier_sortie))

        assert resultat.succes is True
        dossier_rapport = os.path.join(str(dossier_sortie), "rapport")
        assert os.path.isdir(dossier_rapport)
        assert resultat.chemin_json.startswith(dossier_rapport)
        assert resultat.chemin_pdf.startswith(dossier_rapport)

    def test_pipeline_contenu_json_valide(self, dossier_geojson):
        """Le fichier JSON produit contient des resultats valides."""
        resultat = executer_pipeline(str(dossier_geojson))

        with open(resultat.chemin_json, encoding="utf-8") as f:
            donnees = json.load(f)

        assert donnees["succes"] is True
        assert len(donnees["resultats"]) == 2
        ids = {r["id"] for r in donnees["resultats"]}
        assert ids == {"cable_pipe_1", "cable_pipe_2"}

    def test_pipeline_avec_aerien(self, dossier_geojson_avec_aerien):
        """Pipeline avec cheminement aerien : correction appliquee."""
        resultat = executer_pipeline(str(dossier_geojson_avec_aerien))

        assert resultat.succes is True

        with open(resultat.chemin_json, encoding="utf-8") as f:
            donnees = json.load(f)

        cables = {r["id"]: r for r in donnees["resultats"]}

        # Cable BT aerien Reticulee : taux = 5 %
        cable_bt = cables["cable_pipe_1"]
        assert cable_bt["taux_aerien"] == pytest.approx(0.05)
        assert cable_bt["correction_aerien"] == pytest.approx(5.0)

        # Cable HTA non aerien : pas de correction
        cable_hta = cables["cable_pipe_2"]
        assert cable_hta["taux_aerien"] == pytest.approx(0.0)
        assert cable_hta["correction_aerien"] == pytest.approx(0.0)

    def test_pipeline_cree_dossier_rapport(self, dossier_geojson):
        """Le sous-dossier rapport/ est cree automatiquement."""
        resultat = executer_pipeline(str(dossier_geojson))
        assert resultat.succes is True
        assert os.path.isdir(os.path.join(str(dossier_geojson), "rapport"))
