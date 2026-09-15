"""
Tests du codage couleur des priorites dans le rapport PDF.

Le document lui-meme n'est pas relu (ReportLab produit un binaire) : les tests
portent sur les fonctions pures qui construisent les commandes de style
TableStyle, ou se decide la couleur affichee.

Convention verifiee : chaque niveau du verificateur porte sa couleur — rouge
sombre bloquante, rouge forte, orange moyenne, jaune basse, gris inconnue — et
seules les priorites declassantes sont mises en gras.
"""

from reportlab.graphics.shapes import Polygon, String

from recostar.controle.rapport_pdf import (
    ALERTES_JEU,
    BLANC,
    COTE_ALERTE,
    COULEURS_PRIORITE,
    GRIS_DOUX,
    JAUNE,
    MARQUE_ALERTE,
    ORANGE,
    POLICE_GRASSE,
    PREMIERE_COLONNE_PRIORITE,
    ROUGE,
    ROUGE_SOMBRE,
    _alertes_jeu,
    _commandes_couleur_priorite,
    _commandes_priorites_ligne,
    _pictogramme_alerte,
    _priorite_dominante,
)
from recostar.controle.synthese_controles import (
    ORDRE_PRIORITES,
    PRIORITE_BASSE,
    PRIORITE_BLOQUANTE,
    PRIORITE_FORTE,
    PRIORITE_INCONNUE,
    PRIORITE_MOYENNE,
    ResultatControle,
    ResultatFamille,
)


def _famille(priorites: dict[str, int], execute: bool = True) -> ResultatFamille:
    """Famille portant un unique controle a la ventilation demandee."""
    controle = ResultatControle(
        code="E-5201",
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

    def test_moyenne_est_orange(self) -> None:
        """Exigence explicite : les anomalies moyennes apparaissent en orange."""
        assert COULEURS_PRIORITE[PRIORITE_MOYENNE] == ORANGE

    def test_forte_est_rouge(self) -> None:
        assert COULEURS_PRIORITE[PRIORITE_FORTE] == ROUGE

    def test_bloquante_est_rouge_sombre(self) -> None:
        """Le niveau bloquante, jamais emis par star-engine, reste discernable de forte."""
        assert COULEURS_PRIORITE[PRIORITE_BLOQUANTE] == ROUGE_SOMBRE

    def test_basse_est_jaune(self) -> None:
        assert COULEURS_PRIORITE[PRIORITE_BASSE] == JAUNE

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
        assert _priorite_dominante({PRIORITE_MOYENNE: 0}) is None

    def test_priorite_unique(self) -> None:
        assert _priorite_dominante({PRIORITE_MOYENNE: 7}) == PRIORITE_MOYENNE

    def test_bloquant_prime_sur_majeur(self) -> None:
        assert _priorite_dominante({PRIORITE_MOYENNE: 19, PRIORITE_FORTE: 1}) == PRIORITE_FORTE

    def test_majeur_prime_sur_information(self) -> None:
        assert _priorite_dominante({PRIORITE_BASSE: 30, PRIORITE_MOYENNE: 1}) == PRIORITE_MOYENNE

    def test_ordre_respecte_l_echelle(self) -> None:
        """La dominante suit ORDRE_PRIORITES, pas l'ordre d'insertion du dict."""
        ventilation = dict.fromkeys(reversed(ORDRE_PRIORITES), 1)
        assert _priorite_dominante(ventilation) == ORDRE_PRIORITES[0]


class TestCommandesCouleurPriorite:
    """Commandes de style produites pour une cellule."""

    def test_couleur_appliquee(self) -> None:
        commandes = _commandes_couleur_priorite(PRIORITE_MOYENNE, 2, 3)
        assert _couleurs(commandes) == [ORANGE]

    def test_cellule_ciblee(self) -> None:
        commandes = _commandes_couleur_priorite(PRIORITE_MOYENNE, 2, 3)
        assert commandes[0][1] == (2, 3)
        assert commandes[0][2] == (2, 3)

    def test_declassante_mise_en_gras(self) -> None:
        commandes = _commandes_couleur_priorite(PRIORITE_FORTE, 2, 1)
        assert any(c[0] == "FONTNAME" and c[3] == POLICE_GRASSE for c in commandes)

    def test_majeur_non_mise_en_gras(self) -> None:
        """La graisse distingue ce qui declasse ; le majeur ne declasse pas."""
        commandes = _commandes_couleur_priorite(PRIORITE_MOYENNE, 2, 1)
        assert all(c[0] != "FONTNAME" for c in commandes)

    def test_priorite_hors_table_retombe_sur_gris(self) -> None:
        assert _couleurs(_commandes_couleur_priorite("inexistante", 2, 1)) == [GRIS_DOUX]


class TestCommandesPrioritesLigne:
    """Coloration des colonnes de comptage d'une ligne de synthese."""

    def test_famille_non_executee_sans_commande(self) -> None:
        """Les cellules affichent un tiret : rien a colorer."""
        famille = _famille({}, execute=False)
        assert _commandes_priorites_ligne(famille, (PRIORITE_FORTE,), 1) == []

    def test_famille_sans_anomalie_sans_commande(self) -> None:
        assert _commandes_priorites_ligne(_famille({}), (PRIORITE_FORTE,), 1) == []

    def test_colonne_majeure_coloree_en_orange(self) -> None:
        """Regression : seule la colonne bloquante etait coloree auparavant."""
        famille = _famille({PRIORITE_MOYENNE: 19})
        commandes = _commandes_priorites_ligne(famille, (PRIORITE_MOYENNE,), 1)
        assert _couleurs(commandes) == [ORANGE]

    def test_indice_de_colonne_decale(self) -> None:
        """La deuxieme priorite affichee occupe la colonne suivante."""
        famille = _famille({PRIORITE_BASSE: 4})
        commandes = _commandes_priorites_ligne(famille, (PRIORITE_MOYENNE, PRIORITE_BASSE), 2)
        assert commandes[0][1] == (PREMIERE_COLONNE_PRIORITE + 1, 2)

    def test_seules_les_colonnes_alimentees_sont_colorees(self) -> None:
        famille = _famille({PRIORITE_MOYENNE: 19})
        commandes = _commandes_priorites_ligne(famille, (PRIORITE_FORTE, PRIORITE_MOYENNE), 1)
        assert _couleurs(commandes) == [ORANGE]
        assert commandes[0][1] == (PREMIERE_COLONNE_PRIORITE + 1, 1)

    def test_plusieurs_colonnes_colorees(self) -> None:
        famille = _famille({PRIORITE_FORTE: 1, PRIORITE_MOYENNE: 19})
        commandes = _commandes_priorites_ligne(famille, (PRIORITE_FORTE, PRIORITE_MOYENNE), 1)
        assert _couleurs(commandes) == [ROUGE, ORANGE]


def _famille_jeu(*codes_en_anomalie: str) -> ResultatFamille:
    """Famille de structuration portant les deux constats de jeu."""
    controles = tuple(
        ResultatControle(
            code=code,
            libelle=ALERTES_JEU[code],
            succes=True,
            nombre_anomalies=1 if code in codes_en_anomalie else 0,
            anomalies_par_priorite={},
        )
        for code in ("E0120", "E-9701")
    )
    return ResultatFamille("structuration", "Structuration", controles)


class TestAlertesJeu:
    """Les constats portant sur la livraison remontent en tete du rapport."""

    def test_aucune_alerte_si_conforme(self) -> None:
        """Sans constat relevé, aucun bandeau n'est composé."""
        assert _alertes_jeu((_famille_jeu(),)) == []

    def test_alerte_statut(self) -> None:
        """Le constat de statut produit son message."""
        messages = _alertes_jeu((_famille_jeu("E0120"),))
        assert messages == [ALERTES_JEU["E0120"]]

    def test_alerte_altimetrie(self) -> None:
        """Le constat d'altimétrie produit le sien, depuis sa propre famille."""
        assert _alertes_jeu((_famille_jeu("E-9701"),)) == [ALERTES_JEU["E-9701"]]

    def test_deux_alertes(self) -> None:
        """Les deux constats coexistent, dans l'ordre des contrôles."""
        assert _alertes_jeu((_famille_jeu("E0120", "E-9701"),)) == [
            ALERTES_JEU["E0120"],
            ALERTES_JEU["E-9701"],
        ]

    def test_autres_controles_ignores(self) -> None:
        """Un contrôle ordinaire en anomalie ne déclenche aucun bandeau."""
        assert _alertes_jeu((_famille({PRIORITE_MOYENNE: 3}),)) == []

    def test_series_de_codes_equivalentes(self) -> None:
        """Le constat de structuration porte le même message dans les deux versions."""
        assert ALERTES_JEU["E0020"] == ALERTES_JEU["E0120"]

    def test_constat_altimetrie_sous_son_code_verificateur(self) -> None:
        """Le constat d'altimétrie n'a qu'un code : celui du vérificateur."""
        assert "E-9701" in ALERTES_JEU
        assert not any(code.startswith("E01") and "altim" in ALERTES_JEU[code].lower() for code in ALERTES_JEU)


def _formes_alerte(cote: float = COTE_ALERTE) -> tuple[Polygon, String]:
    """Triangle et marque du pictogramme, ramenes a leur type pour l'inspection."""
    triangle, marque = _pictogramme_alerte(cote).contents
    assert isinstance(triangle, Polygon)
    assert isinstance(marque, String)
    return triangle, marque


class TestPictogrammeAlerte:
    """Le triangle d'alerte est tracé en primitives, sans police ni image."""

    def test_dessin_carre(self) -> None:
        """Le pictogramme occupe un carré de la taille demandée."""
        dessin = _pictogramme_alerte()
        assert (dessin.width, dessin.height) == (COTE_ALERTE, COTE_ALERTE)

    def test_triangle_rouge(self) -> None:
        """Le triangle porte la couleur d'alerte."""
        triangle, _ = _formes_alerte()
        assert triangle.fillColor == ROUGE
        # Trois sommets, soit six coordonnees.
        assert len(triangle.points) == 6

    def test_marque_blanche_centree(self) -> None:
        """La marque est posée au centre du triangle, en blanc."""
        _, marque = _formes_alerte()
        assert marque.text == MARQUE_ALERTE
        assert marque.fillColor == BLANC
        assert marque.textAnchor == "middle"
        assert marque.x == COTE_ALERTE / 2

    def test_taille_proportionnelle(self) -> None:
        """Les proportions suivent le côté : le pictogramme reste juste à toute taille."""
        _, petite = _formes_alerte(COTE_ALERTE)
        _, grande = _formes_alerte(COTE_ALERTE * 2)
        assert grande.fontSize == petite.fontSize * 2
