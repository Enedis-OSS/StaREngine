"""
Tests de la lecture des metadonnees du jeu de donnees (_metadata.json).

Couvre :
  - la lecture du bloc Metadata et sa tolerance aux fichiers absents ou malformes
  - le formatage de la date de creation en JJ/MM/AAAA
  - la construction des couples (libelle, valeur) affiches dans le rapport

L'exigence structurante est la tolerance : l'absence ou la corruption de
_metadata.json ne doit jamais empecher la production du rapport de controle.
"""

import json
from pathlib import Path

from metadonnees_jeu import (
    BLOC_METADATA,
    CHAMPS_AFFICHES,
    FICHIER_METADATA,
    LIBELLE_FICHIER_GML,
    LIBELLE_NUMERO_AFFAIRE,
    VALEUR_ABSENTE,
    champs_affichables,
    formater_date,
    lire_metadonnees,
)

# Bloc Metadata complet, tel que produit par la conversion GML vers GeoJSON.
_METADATA_COMPLET = {
    "Datecreation": "2026-05-11",
    "Logiciel": "LAZio",
    "Producteur": "TEST",
    "Responsable": "TEST",
    "SRS": "EPSG:2154",
}


def _ecrire_metadata(repertoire: Path, contenu: object) -> None:
    """Ecrit un _metadata.json de contenu arbitraire dans le repertoire."""
    (repertoire / FICHIER_METADATA).write_text(
        json.dumps(contenu, ensure_ascii=False),
        encoding="utf-8",
    )


class TestLireMetadonnees:
    """Lecture du bloc Metadata."""

    def test_fichier_complet(self, tmp_path: Path) -> None:
        _ecrire_metadata(tmp_path, {BLOC_METADATA: _METADATA_COMPLET})
        assert lire_metadonnees(tmp_path) == _METADATA_COMPLET

    def test_fichier_absent(self, tmp_path: Path) -> None:
        """Cas courant : le rapport doit rester produit sans metadonnees."""
        assert lire_metadonnees(tmp_path) == {}

    def test_repertoire_inexistant(self, tmp_path: Path) -> None:
        assert lire_metadonnees(tmp_path / "absent") == {}

    def test_json_malforme(self, tmp_path: Path) -> None:
        (tmp_path / FICHIER_METADATA).write_text('{"Metadata": ', encoding="utf-8")
        assert lire_metadonnees(tmp_path) == {}

    def test_racine_non_objet(self, tmp_path: Path) -> None:
        _ecrire_metadata(tmp_path, ["pas", "un", "objet"])
        assert lire_metadonnees(tmp_path) == {}

    def test_bloc_metadata_absent(self, tmp_path: Path) -> None:
        _ecrire_metadata(tmp_path, {"ReseauUtilite": {"Nom": "TEST"}})
        assert lire_metadonnees(tmp_path) == {}

    def test_bloc_metadata_non_objet(self, tmp_path: Path) -> None:
        _ecrire_metadata(tmp_path, {BLOC_METADATA: "chaine"})
        assert lire_metadonnees(tmp_path) == {}

    def test_valeurs_converties_en_chaines(self, tmp_path: Path) -> None:
        """Le SRS pourrait etre ecrit comme un nombre : l'affichage attend du texte."""
        _ecrire_metadata(tmp_path, {BLOC_METADATA: {"SRS": 2154}})
        assert lire_metadonnees(tmp_path) == {"SRS": "2154"}

    def test_valeurs_nulles_ecartees(self, tmp_path: Path) -> None:
        """Un champ a null vaut absence, pas la chaine « None »."""
        _ecrire_metadata(tmp_path, {BLOC_METADATA: {"Logiciel": None, "SRS": "EPSG:2154"}})
        assert lire_metadonnees(tmp_path) == {"SRS": "EPSG:2154"}

    def test_bloc_reseau_utilite_ignore(self, tmp_path: Path) -> None:
        """Seul le bloc Metadata est restitue ; ReseauUtilite ne l'est pas."""
        _ecrire_metadata(
            tmp_path,
            {BLOC_METADATA: {"SRS": "EPSG:2154"}, "ReseauUtilite": {"Nom": "TEST"}},
        )
        assert lire_metadonnees(tmp_path) == {"SRS": "EPSG:2154"}


class TestFormaterDate:
    """Mise au format francais de la date de creation."""

    def test_date_iso(self) -> None:
        assert formater_date("2026-05-11") == "11/05/2026"

    def test_date_non_iso_conservee(self) -> None:
        """Mieux vaut restituer la donnee brute qu'en masquer le format inattendu."""
        assert formater_date("11/05/2026") == "11/05/2026"

    def test_valeur_vide_conservee(self) -> None:
        assert formater_date("") == ""

    def test_date_invalide_conservee(self) -> None:
        assert formater_date("2026-13-45") == "2026-13-45"


class TestChampsAffichables:
    """Construction des couples (libelle, valeur) du rapport."""

    def test_tous_les_champs_demandes(self) -> None:
        lignes = champs_affichables(_METADATA_COMPLET)
        assert [libelle for libelle, _ in lignes] == [libelle for _, libelle in CHAMPS_AFFICHES]

    def test_valeurs_du_jeu_de_reference(self) -> None:
        """Valeurs attendues sur l'echantillon fourni."""
        assert champs_affichables(_METADATA_COMPLET) == [
            ("Date de création du fichier RecoStaR", "11/05/2026"),
            ("Logiciel", "LAZio"),
            ("Producteur", "TEST"),
            ("Responsable", "TEST"),
            ("SRS", "EPSG:2154"),
        ]

    def test_libelle_de_date_leve_l_ambiguite(self) -> None:
        """Le bandeau du rapport porte sa propre date de generation.

        Le libelle doit donc rattacher explicitement la date au fichier RecoStaR,
        sans quoi les deux dates seraient confondues.
        """
        libelle = champs_affichables(_METADATA_COMPLET)[0][0]
        assert "RecoStaR" in libelle

    def test_champ_manquant_signale(self) -> None:
        lignes = dict(champs_affichables({"SRS": "EPSG:2154"}))
        assert lignes["Logiciel"] == VALEUR_ABSENTE
        assert lignes["SRS"] == "EPSG:2154"

    def test_champ_vide_signale(self) -> None:
        lignes = dict(champs_affichables({"Producteur": "   "}))
        assert lignes["Producteur"] == VALEUR_ABSENTE

    def test_metadonnees_absentes(self) -> None:
        """Sans metadonnees, toutes les lignes restent affichees en « non renseigné »."""
        lignes = champs_affichables({})
        assert len(lignes) == len(CHAMPS_AFFICHES)
        assert {valeur for _, valeur in lignes} == {VALEUR_ABSENTE}

    def test_champ_hors_liste_ignore(self) -> None:
        """Un champ du fichier non declare dans CHAMPS_AFFICHES n'est pas affiche."""
        lignes = dict(champs_affichables({**_METADATA_COMPLET, "Theme": "ELECTRD"}))
        assert "Theme" not in lignes

    def test_valeurs_encadrees_nettoyees(self) -> None:
        lignes = dict(champs_affichables({"Logiciel": "  LAZio  "}))
        assert lignes["Logiciel"] == "LAZio"


class TestContexteExecution:
    """Fichier GML et numero d'affaire, issus de la ligne de commande.

    Contrairement aux champs de _metadata.json, ces deux informations ne sont
    affichees que si elles sont fournies : leur absence correspond a un mode
    d'execution legitime et non a une metadonnee manquante.
    """

    def test_gml_absent_aucune_ligne(self) -> None:
        libelles = [libelle for libelle, _ in champs_affichables(_METADATA_COMPLET)]
        assert LIBELLE_FICHIER_GML not in libelles

    def test_numero_absent_aucune_ligne(self) -> None:
        libelles = [libelle for libelle, _ in champs_affichables(_METADATA_COMPLET)]
        assert LIBELLE_NUMERO_AFFAIRE not in libelles

    def test_gml_affiche_par_son_nom_seul(self) -> None:
        """Le chemin complet serait illisible dans un encadre : seul le nom compte.

        Le chemin n'est jamais lu : seule sa derniere composante est exploitee.
        """
        lignes = dict(champs_affichables(_METADATA_COMPLET, chemin_gml=Path("/donnees/affaire/recolement.gml")))
        assert lignes[LIBELLE_FICHIER_GML] == "recolement.gml"

    def test_numero_affiche(self) -> None:
        lignes = dict(champs_affichables(_METADATA_COMPLET, numero_affaire="RAC-ABC-24-000001"))
        assert lignes[LIBELLE_NUMERO_AFFAIRE] == "RAC-ABC-24-000001"

    def test_numero_vide_traite_comme_absent(self) -> None:
        """argparse fournit une chaine vide si l'option est passee sans valeur."""
        libelles = [libelle for libelle, _ in champs_affichables(_METADATA_COMPLET, numero_affaire="")]
        assert LIBELLE_NUMERO_AFFAIRE not in libelles

    def test_numero_encadre_nettoye(self) -> None:
        lignes = dict(champs_affichables(_METADATA_COMPLET, numero_affaire="  RAC-ABC-24-000001  "))
        assert lignes[LIBELLE_NUMERO_AFFAIRE] == "RAC-ABC-24-000001"

    def test_contexte_place_en_tete(self) -> None:
        """Le contexte designe ce qui a ete controle : il precede les metadonnees."""
        lignes = champs_affichables(
            _METADATA_COMPLET,
            chemin_gml=Path("recolement.gml"),
            numero_affaire="RAC-ABC-24-000001",
        )
        assert [libelle for libelle, _ in lignes[:2]] == [LIBELLE_FICHIER_GML, LIBELLE_NUMERO_AFFAIRE]

    def test_metadonnees_toujours_completes(self) -> None:
        """L'ajout du contexte ne retire aucune ligne de metadonnees."""
        lignes = champs_affichables(_METADATA_COMPLET, chemin_gml=Path("x.gml"), numero_affaire="RAC")
        assert len(lignes) == len(CHAMPS_AFFICHES) + 2

    def test_contexte_sans_metadonnees(self) -> None:
        """Un GML controle sans _metadata.json reste identifie dans le rapport."""
        lignes = dict(champs_affichables({}, chemin_gml=Path("recolement.gml")))
        assert lignes[LIBELLE_FICHIER_GML] == "recolement.gml"
        assert lignes["Logiciel"] == VALEUR_ABSENTE
