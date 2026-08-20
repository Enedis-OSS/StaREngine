"""
Tests des points d'entrée V1.0 (contrôles E010 à E014).

Ces tests vérifient le contrat des points d'entrée V1.0 :
- ils délèguent au moteur du contrôle V1.1 correspondant, sans logique propre ;
- ils figent la version 1.0, sans exposer d'option `--version` ;
- les rapports produits portent le code E01x (nom de fichier et `type_controle`),
  y compris lorsque le GML analysé annonce une autre version.

Ils couvrent aussi la bascule de nommage des rapports des moteurs eux-mêmes,
qui suit désormais la version contrôlée.
"""

from pathlib import Path

import controle_e010
import controle_e011
import controle_e012
import controle_e013
import controle_e014
import controle_e110
import controle_e111
import controle_e112
import controle_e113
import controle_e114
import pytest

# Couples (point d'entrée V1.0, moteur V1.1) attendus.
POINTS_ENTREE = (
    (controle_e010, controle_e110),
    (controle_e011, controle_e111),
    (controle_e012, controle_e112),
    (controle_e013, controle_e113),
    (controle_e014, controle_e114),
)

# Moteurs produisant un rapport à partir d'une simple liste d'erreurs
# (E112 est exclu : sa signature comporte le chemin du XSD).
MOTEURS_SIMPLES = (
    (controle_e110, "e110", "e010"),
    (controle_e111, "e111", "e011"),
    (controle_e113, "e113", "e013"),
    (controle_e114, "e114", "e014"),
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
        chemin = controle_e112.generer_rapport(chemin_gml_vide, chemin_gml_vide, [], None, "1.0")
        assert chemin.name.endswith("_controle_e012.json")

    def test_rapport_v1_1(self, chemin_gml_vide: Path) -> None:
        chemin = controle_e112.generer_rapport(chemin_gml_vide, chemin_gml_vide, [], None, "1.1")
        assert chemin.name.endswith("_controle_e112.json")

    def test_type_controle_suit_la_version(self, chemin_gml_vide: Path) -> None:
        rapport = controle_e112._construire_rapport(chemin_gml_vide, chemin_gml_vide, [], "1.0")
        assert rapport["type_controle"] == "E012_XSD_NATIF"
