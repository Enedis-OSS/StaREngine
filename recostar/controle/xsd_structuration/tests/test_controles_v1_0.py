"""
Tests des points d'entrée V1.0 (contrôles E0010 à E0014).

Ces tests vérifient le contrat des points d'entrée V1.0 :
- ils délèguent au moteur du contrôle V1.1 correspondant, sans logique propre ;
- ils figent la version 1.0, sans exposer d'option `--version` ;
- les rapports produits portent le code E001x (nom de fichier et `type_controle`),
  y compris lorsque le GML analysé annonce une autre version.

Ils couvrent aussi la bascule de nommage des rapports des moteurs eux-mêmes,
qui suit désormais la version contrôlée.
"""

from pathlib import Path

import pytest

from recostar.controle.xsd_structuration import (
    e0010,
    e0011,
    e0012,
    e0013,
    e0014,
    e0110,
    e0111,
    e0112,
    e0113,
    e0114,
)

# Couples (point d'entrée V1.0, moteur V1.1) attendus.
POINTS_ENTREE = (
    (e0010, e0110),
    (e0011, e0111),
    (e0012, e0112),
    (e0013, e0113),
    (e0014, e0114),
)

# Moteurs produisant un rapport à partir d'une simple liste d'erreurs
# (E0112 est exclu : sa signature comporte le chemin du XSD).
MOTEURS_SIMPLES = (
    (e0110, "e0110", "e0010"),
    (e0111, "e0111", "e0011"),
    (e0113, "e0113", "e0013"),
    (e0114, "e0114", "e0014"),
)


class TestContratPointsEntree:
    """Les cinq points d'entrée V1.0 exposent le même contrat minimal."""

    @pytest.mark.parametrize(("point_entree", "moteur"), POINTS_ENTREE)
    def test_version_figee_a_1_0(self, point_entree, moteur) -> None:
        assert point_entree.VERSION == "1.0"

    @pytest.mark.parametrize(("point_entree", "moteur"), POINTS_ENTREE)
    def test_expose_un_main(self, point_entree, moteur) -> None:
        assert callable(point_entree.main)

    @pytest.mark.parametrize(("point_entree", "moteur"), POINTS_ENTREE)
    def test_delegue_au_moteur_v1_1(self, point_entree, moteur, monkeypatch) -> None:
        """main() appelle le main du moteur V1.1 en imposant la version 1.0."""
        appels: list[str | None] = []
        monkeypatch.setattr(point_entree, "_main", lambda version_imposee=None: appels.append(version_imposee))
        point_entree.main()
        assert appels == ["1.0"]

    @pytest.mark.parametrize(("point_entree", "moteur"), POINTS_ENTREE)
    def test_aucune_logique_de_controle_dupliquee(self, point_entree, moteur) -> None:
        """Le point d'entrée ne redéfinit ni analyseur ni générateur de rapport."""
        propres = {nom for nom in vars(point_entree) if not nom.startswith("_")}
        assert propres <= {"main", "VERSION", "PROFIL_V1_0"}


class TestNommageDesRapports:
    """Le nom du rapport et le type_controle suivent la version contrôlée."""

    @pytest.mark.parametrize(("moteur", "code_v1_1", "code_v1_0"), MOTEURS_SIMPLES)
    def test_rapport_v1_1(self, moteur, code_v1_1, code_v1_0, chemin_gml_vide: Path) -> None:
        chemin = moteur.generer_rapport(chemin_gml_vide, [], None, "1.1")
        assert chemin.name.endswith(f"_controle_{code_v1_1}.json")

    @pytest.mark.parametrize(("moteur", "code_v1_1", "code_v1_0"), MOTEURS_SIMPLES)
    def test_rapport_v1_0(self, moteur, code_v1_1, code_v1_0, chemin_gml_vide: Path) -> None:
        chemin = moteur.generer_rapport(chemin_gml_vide, [], None, "1.0")
        assert chemin.name.endswith(f"_controle_{code_v1_0}.json")

    @pytest.mark.parametrize(("moteur", "code_v1_1", "code_v1_0"), MOTEURS_SIMPLES)
    def test_type_controle_suit_la_version(self, moteur, code_v1_1, code_v1_0, chemin_gml_vide: Path) -> None:
        rapport_v0 = moteur._construire_rapport(chemin_gml_vide, [], "1.0")
        rapport_v1 = moteur._construire_rapport(chemin_gml_vide, [], "1.1")
        assert rapport_v0["type_controle"].startswith(code_v1_0.upper())
        assert rapport_v1["type_controle"].startswith(code_v1_1.upper())

    @pytest.mark.parametrize(("moteur", "code_v1_1", "code_v1_0"), MOTEURS_SIMPLES)
    def test_les_deux_versions_coexistent(self, moteur, code_v1_1, code_v1_0, chemin_gml_vide: Path) -> None:
        """Contrôler les deux versions d'un même GML n'écrase aucun rapport."""
        chemin_v0 = moteur.generer_rapport(chemin_gml_vide, [], None, "1.0")
        chemin_v1 = moteur.generer_rapport(chemin_gml_vide, [], None, "1.1")
        assert chemin_v0 != chemin_v1
        assert chemin_v0.is_file() and chemin_v1.is_file()


class TestNommageRapportXsdNatif:
    """Cas particulier du contrôle XSD natif, dont le rapport porte le XSD."""

    def test_rapport_v1_0(self, chemin_gml_vide: Path) -> None:
        chemin = e0112.generer_rapport(chemin_gml_vide, chemin_gml_vide, [], None, "1.0")
        assert chemin.name.endswith("_controle_e0012.json")

    def test_rapport_v1_1(self, chemin_gml_vide: Path) -> None:
        chemin = e0112.generer_rapport(chemin_gml_vide, chemin_gml_vide, [], None, "1.1")
        assert chemin.name.endswith("_controle_e0112.json")

    def test_type_controle_suit_la_version(self, chemin_gml_vide: Path) -> None:
        rapport = e0112._construire_rapport(chemin_gml_vide, chemin_gml_vide, [], "1.0")
        assert rapport["type_controle"] == "E0012_XSD_NATIF"
