"""
Tests unitaires du module rapport_commun.

Couvre la construction, l'écriture et le nommage des rapports JSON partagés
par les contrôles E110 à E114.
"""

import json
from pathlib import Path

import pytest
from rapport_commun import (
    NIVEAU_CONTROLE,
    compter_par_severite,
    construire_rapport,
    ecrire_rapport,
    generer_rapport,
    resoudre_chemin_rapport,
)


class _ErreurFactice:
    """Erreur minimale conforme au protocole ErreurRapportable."""

    __slots__ = ("code", "severite")

    def __init__(self, code: str = "CODE", severite: str = "ERREUR") -> None:
        self.code = code
        self.severite = severite

    def vers_dict(self) -> dict:
        return {"code": self.code, "severite": self.severite}


@pytest.fixture
def chemin_gml(tmp_path: Path) -> Path:
    """Fichier GML vide servant de source de rapport."""
    chemin = tmp_path / "fichier.gml"
    chemin.write_text("<vide/>", encoding="utf-8")
    return chemin


# ---------------------------------------------------------------------------
# compter_par_severite
# ---------------------------------------------------------------------------


class TestCompterParSeverite:
    """Ventilation des erreurs par sévérité."""

    def test_liste_vide(self):
        assert compter_par_severite([]) == {}

    def test_severite_unique(self):
        assert compter_par_severite([_ErreurFactice()] * 3) == {"ERREUR": 3}

    def test_severites_multiples(self):
        """Le comptage reste correct si une sévérité complémentaire apparaît."""
        erreurs = [
            _ErreurFactice(severite="ERREUR"),
            _ErreurFactice(severite="ERREUR"),
            _ErreurFactice(severite="AVERTISSEMENT"),
        ]
        assert compter_par_severite(erreurs) == {"ERREUR": 2, "AVERTISSEMENT": 1}


# ---------------------------------------------------------------------------
# resoudre_chemin_rapport
# ---------------------------------------------------------------------------


class TestResoudreCheminRapport:
    """Emplacement et nommage du rapport JSON."""

    def test_sans_repertoire_sortie(self, chemin_gml: Path):
        chemin = resoudre_chemin_rapport(chemin_gml, None, "_controle_e110.json")
        assert chemin.parent == chemin_gml.parent

    def test_avec_repertoire_sortie(self, chemin_gml: Path, tmp_path: Path):
        dossier = tmp_path / "out"
        dossier.mkdir()
        chemin = resoudre_chemin_rapport(chemin_gml, dossier, "_controle_e110.json")
        assert chemin.parent == dossier

    def test_nom_derive_du_gml(self, chemin_gml: Path):
        chemin = resoudre_chemin_rapport(chemin_gml, None, "_controle_e113.json")
        assert chemin.name == "fichier_controle_e113.json"

    def test_chemin_absolu(self, chemin_gml: Path):
        """Le chemin retourné est toujours résolu, jamais relatif."""
        chemin = resoudre_chemin_rapport(chemin_gml, None, "_controle_e110.json")
        assert chemin.is_absolute()


# ---------------------------------------------------------------------------
# construire_rapport
# ---------------------------------------------------------------------------


class TestConstruireRapport:
    """Structure et contenu du dictionnaire de rapport."""

    def test_champs_attendus(self, chemin_gml: Path):
        rapport = construire_rapport(chemin_gml, "E110_ORDRE", [], "1.1")
        assert set(rapport.keys()) == {
            "fichier",
            "date_controle",
            "niveau",
            "type_controle",
            "version_controlee",
            "conformite",
            "nb_erreurs",
            "nb_par_severite",
            "erreurs",
        }

    def test_conforme_si_aucune_erreur(self, chemin_gml: Path):
        rapport = construire_rapport(chemin_gml, "E110_ORDRE", [], "1.1")
        assert rapport["conformite"] == "CONFORME"
        assert rapport["nb_erreurs"] == 0
        assert rapport["nb_par_severite"] == {}

    def test_non_conforme_avec_erreurs(self, chemin_gml: Path):
        rapport = construire_rapport(chemin_gml, "E110_ORDRE", [_ErreurFactice()], "1.1")
        assert rapport["conformite"] == "NON_CONFORME"
        assert rapport["nb_erreurs"] == 1
        assert rapport["nb_par_severite"] == {"ERREUR": 1}

    def test_metadonnees_propagees(self, chemin_gml: Path):
        rapport = construire_rapport(chemin_gml, "E113_ENTETE", [], "1.0")
        assert rapport["type_controle"] == "E113_ENTETE"
        assert rapport["version_controlee"] == "1.0"
        assert rapport["niveau"] == NIVEAU_CONTROLE
        assert rapport["fichier"] == str(chemin_gml.resolve())

    def test_erreurs_serialisees(self, chemin_gml: Path):
        rapport = construire_rapport(chemin_gml, "E110_ORDRE", [_ErreurFactice(code="X")], "1.1")
        assert rapport["erreurs"] == [{"code": "X", "severite": "ERREUR"}]

    def test_champs_specifiques_inseres(self, chemin_gml: Path):
        """E112 documente son XSD : le champ suit immédiatement 'fichier'."""
        rapport = construire_rapport(
            chemin_gml,
            "E112_XSD_NATIF",
            [],
            "1.1",
            champs_specifiques={"xsd": "/chemin/schema.xsd"},
        )
        assert rapport["xsd"] == "/chemin/schema.xsd"
        assert list(rapport)[:2] == ["fichier", "xsd"]

    def test_sans_champs_specifiques(self, chemin_gml: Path):
        rapport = construire_rapport(chemin_gml, "E110_ORDRE", [], "1.1", champs_specifiques=None)
        assert "xsd" not in rapport


# ---------------------------------------------------------------------------
# ecrire_rapport et generer_rapport
# ---------------------------------------------------------------------------


class TestEcritureRapport:
    """Sérialisation du rapport sur disque."""

    def test_ecrire_cree_le_fichier(self, tmp_path: Path):
        cible = tmp_path / "rapport.json"
        chemin = ecrire_rapport(cible, {"cle": "valeur"})
        assert chemin == cible
        assert json.loads(cible.read_text(encoding="utf-8")) == {"cle": "valeur"}

    def test_ecrire_preserve_les_accents(self, tmp_path: Path):
        """ensure_ascii=False : les rapports restent lisibles en français."""
        cible = tmp_path / "rapport.json"
        ecrire_rapport(cible, {"message": "élément déjà présent"})
        assert "élément déjà présent" in cible.read_text(encoding="utf-8")

    def test_generer_enchaine_construction_et_ecriture(self, chemin_gml: Path):
        chemin = generer_rapport(
            chemin_gml,
            "E111_METIER",
            "_controle_e111.json",
            [_ErreurFactice()],
            None,
            "1.1",
        )
        assert chemin.name == "fichier_controle_e111.json"
        rapport = json.loads(chemin.read_text(encoding="utf-8"))
        assert rapport["type_controle"] == "E111_METIER"
        assert rapport["conformite"] == "NON_CONFORME"

    def test_generer_respecte_le_repertoire_sortie(self, chemin_gml: Path, tmp_path: Path):
        dossier = tmp_path / "out"
        dossier.mkdir()
        chemin = generer_rapport(chemin_gml, "E110_ORDRE", "_controle_e110.json", [], dossier, "1.1")
        assert chemin.parent == dossier
