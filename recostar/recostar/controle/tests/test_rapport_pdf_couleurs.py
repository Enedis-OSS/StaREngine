"""
Tests du codage couleur des priorites dans le rapport PDF.

Le document lui-meme n'est pas relu (ReportLab produit un binaire) : les tests
portent sur les fonctions pures qui construisent les commandes de style
TableStyle, ou se decide la couleur affichee.

Convention verifiee : chaque priorite porte sa couleur — rouge bloquante, orange
majeure, jaune mineure, bleu information — et seules les priorites declassantes
sont mises en gras.
"""

from rapport_pdf import (
    BLEU,
    COULEURS_PRIORITE,
    GRIS_DOUX,
    JAUNE,
    ORANGE,
    POLICE_GRASSE,
    PREMIERE_COLONNE_PRIORITE,
    ROUGE,
    _commandes_couleur_priorite,
    _commandes_priorites_ligne,
    _priorite_dominante,
)
from synthese_controles import (
    ORDRE_PRIORITES,
    PRIORITE_BLOQUANT,
    PRIORITE_INCONNUE,
    PRIORITE_INFORMATION,
    PRIORITE_MAJEUR,
    PRIORITE_MINEUR,
    ResultatControle,
    ResultatFamille,
)


def _famille(priorites: dict[str, int], execute: bool = True) -> ResultatFamille:
    """Famille portant un unique controle a la ventilation demandee."""
    controle = ResultatControle(
        code="E202",
        libelle="Altimétrie des sommets de câbles",
        succes=True,
        nombre_anomalies=sum(priorites.values()),
        anomalies_par_priorite=priorites,
    )
    return ResultatFamille("altimetrie", "Altimétrie", (controle,), execute=execute)


def _couleurs(commandes: list[tuple]) -> list:
    """Couleurs portees par les commandes TEXTCOLOR."""
    return [c[3] for c in commandes if c[0] == "TEXTCOLOR"]


class TestCouleursPriorite:
    """Table de correspondance priorite -> couleur."""

    def test_majeur_est_orange(self) -> None:
        """Exigence explicite : les anomalies majeures apparaissent en orange."""
        assert COULEURS_PRIORITE[PRIORITE_MAJEUR] == ORANGE

    def test_bloquant_est_rouge(self) -> None:
        assert COULEURS_PRIORITE[PRIORITE_BLOQUANT] == ROUGE

    def test_mineur_est_jaune(self) -> None:
        assert COULEURS_PRIORITE[PRIORITE_MINEUR] == JAUNE

    def test_information_est_bleu(self) -> None:
        assert COULEURS_PRIORITE[PRIORITE_INFORMATION] == BLEU

    def test_priorite_inconnue_est_grise(self) -> None:
        assert COULEURS_PRIORITE[PRIORITE_INCONNUE] == GRIS_DOUX

    def test_toute_priorite_de_l_echelle_a_une_couleur(self) -> None:
        """Une priorite sans couleur retomberait sur un gris indifferencie."""
        assert set(ORDRE_PRIORITES) == set(COULEURS_PRIORITE)

    def test_couleurs_distinctes_par_priorite(self) -> None:
        """Deux priorites de meme couleur seraient indiscernables dans le rapport."""
        couleurs = [c.hexval() for c in COULEURS_PRIORITE.values()]
        assert len(set(couleurs)) == len(couleurs)


class TestPrioriteDominante:
    """Selection de la priorite la plus grave presente."""

    def test_aucune_anomalie(self) -> None:
        assert _priorite_dominante({}) is None

    def test_comptage_nul_ignore(self) -> None:
        """Une priorite declaree a zero n'est pas presente."""
        assert _priorite_dominante({PRIORITE_MAJEUR: 0}) is None

    def test_priorite_unique(self) -> None:
        assert _priorite_dominante({PRIORITE_MAJEUR: 7}) == PRIORITE_MAJEUR

    def test_bloquant_prime_sur_majeur(self) -> None:
        assert _priorite_dominante({PRIORITE_MAJEUR: 19, PRIORITE_BLOQUANT: 1}) == PRIORITE_BLOQUANT

    def test_majeur_prime_sur_information(self) -> None:
        assert _priorite_dominante({PRIORITE_INFORMATION: 30, PRIORITE_MAJEUR: 1}) == PRIORITE_MAJEUR

    def test_ordre_respecte_l_echelle(self) -> None:
        """La dominante suit ORDRE_PRIORITES, pas l'ordre d'insertion du dict."""
        ventilation = dict.fromkeys(reversed(ORDRE_PRIORITES), 1)
        assert _priorite_dominante(ventilation) == ORDRE_PRIORITES[0]


class TestCommandesCouleurPriorite:
    """Commandes de style produites pour une cellule."""

    def test_couleur_appliquee(self) -> None:
        commandes = _commandes_couleur_priorite(PRIORITE_MAJEUR, 2, 3)
        assert _couleurs(commandes) == [ORANGE]

    def test_cellule_ciblee(self) -> None:
        commandes = _commandes_couleur_priorite(PRIORITE_MAJEUR, 2, 3)
        assert commandes[0][1] == (2, 3)
        assert commandes[0][2] == (2, 3)

    def test_declassante_mise_en_gras(self) -> None:
        commandes = _commandes_couleur_priorite(PRIORITE_BLOQUANT, 2, 1)
        assert any(c[0] == "FONTNAME" and c[3] == POLICE_GRASSE for c in commandes)

    def test_majeur_non_mise_en_gras(self) -> None:
        """La graisse distingue ce qui declasse ; le majeur ne declasse pas."""
        commandes = _commandes_couleur_priorite(PRIORITE_MAJEUR, 2, 1)
        assert all(c[0] != "FONTNAME" for c in commandes)

    def test_priorite_hors_table_retombe_sur_gris(self) -> None:
        assert _couleurs(_commandes_couleur_priorite("inexistante", 2, 1)) == [GRIS_DOUX]


class TestCommandesPrioritesLigne:
    """Coloration des colonnes de comptage d'une ligne de synthese."""

    def test_famille_non_executee_sans_commande(self) -> None:
        """Les cellules affichent un tiret : rien a colorer."""
        famille = _famille({}, execute=False)
        assert _commandes_priorites_ligne(famille, (PRIORITE_BLOQUANT,), 1) == []

    def test_famille_sans_anomalie_sans_commande(self) -> None:
        assert _commandes_priorites_ligne(_famille({}), (PRIORITE_BLOQUANT,), 1) == []

    def test_colonne_majeure_coloree_en_orange(self) -> None:
        """Regression : seule la colonne bloquante etait coloree auparavant."""
        famille = _famille({PRIORITE_MAJEUR: 19})
        commandes = _commandes_priorites_ligne(famille, (PRIORITE_MAJEUR,), 1)
        assert _couleurs(commandes) == [ORANGE]

    def test_indice_de_colonne_decale(self) -> None:
        """La deuxieme priorite affichee occupe la colonne suivante."""
        famille = _famille({PRIORITE_INFORMATION: 4})
        commandes = _commandes_priorites_ligne(famille, (PRIORITE_MAJEUR, PRIORITE_INFORMATION), 2)
        assert commandes[0][1] == (PREMIERE_COLONNE_PRIORITE + 1, 2)

    def test_seules_les_colonnes_alimentees_sont_colorees(self) -> None:
        famille = _famille({PRIORITE_MAJEUR: 19})
        commandes = _commandes_priorites_ligne(famille, (PRIORITE_BLOQUANT, PRIORITE_MAJEUR), 1)
        assert _couleurs(commandes) == [ORANGE]
        assert commandes[0][1] == (PREMIERE_COLONNE_PRIORITE + 1, 1)

    def test_plusieurs_colonnes_colorees(self) -> None:
        famille = _famille({PRIORITE_BLOQUANT: 1, PRIORITE_MAJEUR: 19})
        commandes = _commandes_priorites_ligne(famille, (PRIORITE_BLOQUANT, PRIORITE_MAJEUR), 1)
        assert _couleurs(commandes) == [ROUGE, ORANGE]
