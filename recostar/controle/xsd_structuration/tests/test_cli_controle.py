"""
Tests unitaires de l'enveloppe CLI mutualisée (cli_controle).

Couvre le parseur d'arguments commun aux contrôles E0110 à E0114 et la
validation des chemins passés en ligne de commande.

La résolution de profil (`resoudre_profil_cli`, module cli_version) est
couverte par test_multi_version.py.
"""

from pathlib import Path

import pytest

from recostar.controle.xsd_structuration.cli_controle import construire_parseur, valider_arguments
from recostar.controle.xsd_structuration.detection_version import JETON_AUTO
from recostar.controle.xsd_structuration.versions import VERSIONS_SUPPORTEES


@pytest.fixture
def parseur():
    """Parseur commun sans option supplémentaire."""
    return construire_parseur("Description de test")


@pytest.fixture
def chemin_gml(tmp_path: Path) -> Path:
    """Fichier GML existant."""
    chemin = tmp_path / "fichier.gml"
    chemin.write_text("<vide/>", encoding="utf-8")
    return chemin


# ---------------------------------------------------------------------------
# construire_parseur
# ---------------------------------------------------------------------------


class TestConstruireParseur:
    """Arguments déclarés par le parseur commun."""

    def test_fichier_gml_obligatoire(self, parseur, capsys):
        with pytest.raises(SystemExit):
            parseur.parse_args([])
        assert capsys.readouterr().err  # argparse signale l'argument manquant

    def test_fichier_gml_converti_en_path(self, parseur):
        args = parseur.parse_args(["dossier/fichier.gml"])
        assert args.fichier_gml == Path("dossier/fichier.gml")

    def test_output_dir_optionnel(self, parseur):
        args = parseur.parse_args(["fichier.gml"])
        assert args.output_dir is None

    def test_output_dir_converti_en_path(self, parseur):
        args = parseur.parse_args(["fichier.gml", "--output-dir", "sortie"])
        assert args.output_dir == Path("sortie")

    def test_version_par_defaut_auto(self, parseur):
        args = parseur.parse_args(["fichier.gml"])
        assert args.version == JETON_AUTO

    def test_versions_supportees_acceptees(self, parseur):
        for code in VERSIONS_SUPPORTEES:
            args = parseur.parse_args(["fichier.gml", "--version", code])
            assert args.version == code

    def test_version_inconnue_refusee(self, parseur):
        with pytest.raises(SystemExit):
            parseur.parse_args(["fichier.gml", "--version", "9.9"])

    def test_description_propagee(self):
        parseur = construire_parseur("Contrôle E0110 : ordre de structure.")
        assert parseur.description == "Contrôle E0110 : ordre de structure."

    def test_options_specifiques_ajoutables(self, parseur):
        """Les contrôles étendent le parseur commun avec leurs propres options."""
        parseur.add_argument("--xsd", type=Path, default=None)
        args = parseur.parse_args(["fichier.gml", "--xsd", "schema.xsd"])
        assert args.xsd == Path("schema.xsd")


# ---------------------------------------------------------------------------
# valider_arguments
# ---------------------------------------------------------------------------


class TestValiderArguments:
    """Validation et normalisation des chemins CLI."""

    def test_fichier_valide_accepte(self, parseur, chemin_gml: Path):
        args = parseur.parse_args([str(chemin_gml)])
        valider_arguments(args)
        assert args.fichier_gml == chemin_gml.resolve()

    def test_chemin_resolu_en_absolu(self, parseur, chemin_gml: Path):
        """Les contrôles reçoivent toujours un chemin absolu."""
        args = parseur.parse_args([str(chemin_gml)])
        valider_arguments(args)
        assert args.fichier_gml.is_absolute()

    def test_fichier_absent_refuse(self, parseur, tmp_path: Path, capsys):
        args = parseur.parse_args([str(tmp_path / "absent.gml")])
        with pytest.raises(SystemExit) as exc:
            valider_arguments(args)
        assert exc.value.code == 1
        assert "n'existe pas" in capsys.readouterr().err

    def test_repertoire_au_lieu_dun_fichier_refuse(self, parseur, tmp_path: Path, capsys):
        args = parseur.parse_args([str(tmp_path)])
        with pytest.raises(SystemExit) as exc:
            valider_arguments(args)
        assert exc.value.code == 1
        assert "n'est pas un fichier" in capsys.readouterr().err

    def test_output_dir_valide_accepte(self, parseur, chemin_gml: Path, tmp_path: Path):
        dossier = tmp_path / "out"
        dossier.mkdir()
        args = parseur.parse_args([str(chemin_gml), "--output-dir", str(dossier)])
        valider_arguments(args)
        assert args.output_dir == dossier.resolve()

    def test_output_dir_absent_refuse(self, parseur, chemin_gml: Path, tmp_path: Path, capsys):
        args = parseur.parse_args([str(chemin_gml), "--output-dir", str(tmp_path / "absent")])
        with pytest.raises(SystemExit) as exc:
            valider_arguments(args)
        assert exc.value.code == 1
        assert "répertoire de sortie" in capsys.readouterr().err

    def test_output_dir_absent_reste_none(self, parseur, chemin_gml: Path):
        """Sans --output-dir, la valeur reste None (rapport à côté du GML)."""
        args = parseur.parse_args([str(chemin_gml)])
        valider_arguments(args)
        assert args.output_dir is None
