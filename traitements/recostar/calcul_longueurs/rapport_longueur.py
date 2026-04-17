"""
Generation du rapport PDF des longueurs de cables.

Produit un document PDF recapitulatif des longueurs geographiques
et electriques calculees, avec detail des corrections appliquees
par cable. Execute lors du controle qualite avant export GML.

Usage : python rapport_longueur.py --chemin-projet <chemin>
Sortie : fichier PDF dans le dossier rapport/ du projet.
"""

import argparse
import json
import math
import os
import sys
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Dimensions de la page (paysage pour le tableau large)
LARGEUR_PAGE, HAUTEUR_PAGE = landscape(A4)
MARGE = 2.0 * cm

# Labels lisibles pour les types d'entites
LABELS_TYPE_ENTITE: dict[str, str] = {
    "remontee_aero_souterraine": "RAS",
    "poste": "Poste",
    "coffret": "Coffret",
}


def _creer_styles() -> dict[str, ParagraphStyle]:
    """Cree les styles de paragraphe pour le rapport."""
    base = getSampleStyleSheet()
    return {
        "titre": ParagraphStyle(
            "TitreRapport",
            parent=base["Title"],
            fontSize=18,
            spaceAfter=12,
        ),
        "sous_titre": ParagraphStyle(
            "SousTitre",
            parent=base["Heading2"],
            fontSize=14,
            spaceAfter=8,
            spaceBefore=12,
        ),
        "normal": ParagraphStyle(
            "NormalRapport",
            parent=base["Normal"],
            fontSize=10,
            spaceAfter=6,
        ),
        "cellule": ParagraphStyle(
            "CelluleTableau",
            fontSize=8,
            leading=10,
            wordWrap="CJK",
        ),
        "entete": ParagraphStyle(
            "EnteteTableau",
            fontSize=8,
            leading=10,
            wordWrap="CJK",
            textColor=colors.white,
        ),
    }


def _formater_type_entite(type_entite: str) -> str:
    """Convertit un identifiant de type d'entite en label lisible."""
    if not type_entite:
        return "-"
    return LABELS_TYPE_ENTITE.get(type_entite, type_entite)


def _construire_statistiques(
    styles: dict[str, ParagraphStyle],
    resultats: list[dict[str, Any]],
) -> list[Any]:
    """Construit la section de statistiques globales."""
    elements: list[Any] = []

    nb_cables = len(resultats)
    nb_hta = sum(1 for r in resultats if r.get("domaine_tension") == "HTA")
    nb_bt = nb_cables - nb_hta

    longueur_geo_totale = sum(r.get("longueur_geographique", 0) for r in resultats)
    longueur_elec_totale = sum(r.get("longueur_electrique", 0) for r in resultats)

    elements.append(
        Paragraph(
            f"Nombre de cables : <b>{nb_cables}</b> "
            f"(HTA : <b>{nb_hta}</b>, BT : <b>{nb_bt}</b>)",
            styles["normal"],
        )
    )
    elements.append(
        Paragraph(
            f"Longueur geographique totale : <b>{longueur_geo_totale:.1f} m</b>",
            styles["normal"],
        )
    )
    elements.append(
        Paragraph(
            f"Longueur electrique totale : <b>{longueur_elec_totale} m</b>",
            styles["normal"],
        )
    )
    elements.append(Spacer(1, 6 * mm))

    return elements


def _style_tableau() -> TableStyle:
    """Retourne le style commun pour les tableaux du rapport."""
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#374151")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            (
                "ROWBACKGROUNDS",
                (0, 1),
                (-1, -1),
                [colors.white, colors.HexColor("#F3F4F6")],
            ),
        ]
    )


def _construire_tableau_cables(
    styles: dict[str, ParagraphStyle],
    resultats: list[dict[str, Any]],
) -> list[Any]:
    """Construit le tableau recapitulatif des longueurs par cable."""
    elements: list[Any] = []
    elements.append(Paragraph("Detail par cable", styles["sous_titre"]))

    style_entete = styles["entete"]

    # En-tete
    donnees: list[list[Any]] = [
        [
            Paragraph("Cable", style_entete),
            Paragraph("Domaine", style_entete),
            Paragraph("Hierarchie BT", style_entete),
            Paragraph("Statut", style_entete),
            Paragraph("Long. geo (m)", style_entete),
            Paragraph("Long. elec (m)", style_entete),
            Paragraph("Corr. depart", style_entete),
            Paragraph("Type depart", style_entete),
            Paragraph("Corr. arrivee", style_entete),
            Paragraph("Type arrivee", style_entete),
            Paragraph("Corr. aerien", style_entete),
        ]
    ]

    style_cellule = styles["cellule"]

    for resultat in resultats:
        hierarchie = resultat.get("hierarchie_bt", "")
        statut = resultat.get("statut", "")
        type_dep = _formater_type_entite(resultat.get("type_entite_depart", ""))
        type_arr = _formater_type_entite(resultat.get("type_entite_arrivee", ""))
        corr_dep = resultat.get("correction_depart", 0)
        corr_arr = resultat.get("correction_arrivee", 0)
        corr_aer = resultat.get("correction_aerien", 0)
        taux_aer = resultat.get("taux_aerien", 0)

        donnees.append(
            [
                Paragraph(str(resultat.get("id", "")), style_cellule),
                resultat.get("domaine_tension", ""),
                Paragraph(hierarchie if hierarchie else "-", style_cellule),
                Paragraph(statut if statut else "-", style_cellule),
                f"{resultat.get('longueur_geographique', 0):.1f}",
                str(resultat.get("longueur_electrique", 0)),
                f"+{corr_dep:.0f} m" if corr_dep > 0 else "-",
                type_dep,
                f"+{corr_arr:.0f} m" if corr_arr > 0 else "-",
                type_arr,
                f"+{taux_aer:.0%}" if corr_aer > 0 else "-",
            ]
        )

    # Alias du statut de mise en service pour la coloration conditionnelle
    STATUT_MISE_EN_SERVICE = "En attente de mise en service"
    COULEUR_MISE_EN_SERVICE = colors.HexColor("#D1FAE5")

    largeurs = [
        3.8 * cm,
        1.6 * cm,
        2.0 * cm,
        3.0 * cm,
        2.0 * cm,
        2.0 * cm,
        1.8 * cm,
        1.8 * cm,
        1.8 * cm,
        1.8 * cm,
        1.8 * cm,
    ]
    tableau = Table(donnees, colWidths=largeurs)
    tableau.setStyle(_style_tableau())

    # Fond vert leger pour les lignes dont le statut est "En attente de mise en service"
    for idx_ligne, resultat in enumerate(resultats, start=1):
        if resultat.get("statut") == STATUT_MISE_EN_SERVICE:
            tableau.setStyle(
                TableStyle(
                    [
                        (
                            "BACKGROUND",
                            (0, idx_ligne),
                            (-1, idx_ligne),
                            COULEUR_MISE_EN_SERVICE,
                        ),
                    ]
                )
            )

    elements.append(tableau)

    return elements


def generer_rapport_longueur(
    chemin_projet: str,
    resultats: list[dict[str, Any]],
) -> str:
    """Genere le rapport PDF des longueurs dans le dossier rapport/ du projet.

    Retourne le chemin du fichier PDF genere.
    """
    dossier_rapport = os.path.join(chemin_projet, "rapport")
    os.makedirs(dossier_rapport, exist_ok=True)

    chemin_pdf = os.path.join(dossier_rapport, "rapport_longueurs_cables.pdf")
    styles = _creer_styles()

    doc = SimpleDocTemplate(
        chemin_pdf,
        pagesize=landscape(A4),
        leftMargin=MARGE,
        rightMargin=MARGE,
        topMargin=MARGE,
        bottomMargin=MARGE,
    )

    elements: list[Any] = []

    # Titre
    elements.append(Paragraph("Rapport des longueurs de cables", styles["titre"]))
    elements.append(Spacer(1, 6 * mm))

    # Statistiques globales
    elements.extend(_construire_statistiques(styles, resultats))

    # Tableau detail par cable
    elements.extend(_construire_tableau_cables(styles, resultats))

    doc.build(elements)
    return chemin_pdf


def _charger_resultats_longueurs(chemin_projet: str) -> list[dict[str, Any]]:
    """Charge les resultats de longueurs depuis le fichier JSON du dossier rapport/."""
    chemin_json = os.path.join(chemin_projet, "rapport", "resultats_longueurs.json")
    if not os.path.isfile(chemin_json):
        return []
    with open(chemin_json, encoding="utf-8") as fichier:
        donnees = json.load(fichier)
    if not donnees.get("succes"):
        return []
    return donnees.get("resultats", [])


def main() -> None:
    """Point d'entree du script de generation du rapport PDF des longueurs."""
    parseur = argparse.ArgumentParser(
        description="Generation du rapport PDF des longueurs de cables"
    )
    parseur.add_argument(
        "--chemin-projet", required=True, help="Chemin du projet RecoStaR"
    )
    arguments = parseur.parse_args()

    resultats = _charger_resultats_longueurs(arguments.chemin_projet)

    if len(resultats) == 0:
        json.dump(
            {"succes": False, "erreur": "Aucun resultat de longueur disponible"},
            sys.stdout,
            ensure_ascii=False,
        )
        return

    chemin_pdf = generer_rapport_longueur(arguments.chemin_projet, resultats)

    json.dump(
        {"succes": True, "chemin_pdf": chemin_pdf},
        sys.stdout,
        ensure_ascii=False,
    )


if __name__ == "__main__":
    main()
