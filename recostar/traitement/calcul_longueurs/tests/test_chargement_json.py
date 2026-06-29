"""Tests du chargement securise et de la validation des resultats JSON."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chargement_json import (  # type: ignore[import-not-found]
    charger_json_confine,
    valider_resultats_longueurs,
)

# --- charger_json_confine ---


class TestChargerJsonConfine:
    """Tests du chargement JSON confine a un repertoire autorise."""

    def test_charge_json_valide(self, tmp_path):
        """Fichier JSON contenu dans le repertoire : charge le contenu."""
        chemin = tmp_path / "donnees.json"
        chemin.write_text(json.dumps({"cle": "valeur"}), encoding="utf-8")
        assert charger_json_confine(tmp_path, chemin) == {"cle": "valeur"}

    def test_refuse_chemin_hors_repertoire(self, tmp_path):
        """Chemin remontant hors du repertoire autorise : leve ValueError."""
        autorise = tmp_path / "autorise"
        autorise.mkdir()
        intrus = tmp_path / "secret.json"
        intrus.write_text(json.dumps({"x": 1}), encoding="utf-8")
        with pytest.raises(ValueError):
            charger_json_confine(autorise, intrus)

    def test_refuse_traversal_avec_dot_dot(self, tmp_path):
        """Tentative de traversal via '..' : leve ValueError apres resolve."""
        autorise = tmp_path / "autorise"
        autorise.mkdir()
        intrus = tmp_path / "secret.json"
        intrus.write_text(json.dumps({"x": 1}), encoding="utf-8")
        chemin_traversal = autorise / ".." / "secret.json"
        with pytest.raises(ValueError):
            charger_json_confine(autorise, chemin_traversal)

    def test_refuse_extension_non_json(self, tmp_path):
        """Extension differente de .json : leve ValueError."""
        chemin = tmp_path / "donnees.txt"
        chemin.write_text("texte", encoding="utf-8")
        with pytest.raises(ValueError):
            charger_json_confine(tmp_path, chemin)


# --- valider_resultats_longueurs ---


class TestValiderResultatsLongueurs:
    """Tests de la validation de la cle 'resultats'."""

    def test_liste_valide_retournee(self):
        """'resultats' est une liste : retournee telle quelle."""
        donnees = {"resultats": [{"id": "a"}, {"id": "b"}]}
        assert valider_resultats_longueurs(donnees) == [{"id": "a"}, {"id": "b"}]

    def test_cle_absente_retourne_liste_vide(self):
        """'resultats' absent : retourne une liste vide."""
        assert valider_resultats_longueurs({"succes": True}) == []

    def test_non_liste_leve_erreur(self):
        """'resultats' non liste : leve ValueError."""
        with pytest.raises(ValueError):
            valider_resultats_longueurs({"resultats": "pas une liste"})

    def test_depassement_max_leve_erreur(self):
        """Nombre d'elements superieur a la borne : leve ValueError."""
        donnees = {"resultats": [{"id": i} for i in range(11)]}
        with pytest.raises(ValueError):
            valider_resultats_longueurs(donnees, max_elements=10)
