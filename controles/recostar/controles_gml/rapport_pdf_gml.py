"""
Generation du rapport PDF de synthese des controles GML.

Produit un document PDF recapitulatif des resultats de l'ensemble des
controles GML (unicite des identifiants, conformite des valeurs XSD).
Le rapport presente une synthese globale, un tableau recapitulatif par
controle, puis le detail des entites en ecart avec leurs identifiants.

Usage CLI :
    python rapport_pdf_gml.py --repertoire <chemin> [--sortie <chemin>]

Sortie : rapport_controles_gml.pdf
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Nom du fichier PDF de sortie
FICHIER_RAPPORT: str = "rapport_controles_gml.pdf"

# Dimensions de la page
LARGEUR_PAGE, HAUTEUR_PAGE = A4
MARGE = 2.0 * cm

# Configuration des colonnes de detail par controle
# Chaque entree : (cle_propriete, en_tete_colonne, largeur_cm)
_COLONNES_UNICITE_ID: tuple[tuple[str, str, float], ...] = (
    ("id_duplique", "ID duplique", 4.5),
    ("fichier_source", "Fichier source", 5.0),
    ("type_anomalie", "Type anomalie", 3.0),
    ("message", "Message", 4.0),
    ("priorite", "Priorite", 2.0),
)

_COLONNES_VALEUR_XSD: tuple[tuple[str, str, float], ...] = (
    ("id_entite", "ID entite", 4.0),
    ("fichier_source", "Fichier source", 4.5),
    ("type_anomalie", "Type anomalie", 3.0),
    ("message", "Message", 5.0),
    ("priorite", "Priorite", 2.0),
)

# Correspondance entre fichier d'ecarts et configuration du controle
CONTROLES: tuple[tuple[str, str, str, tuple[tuple[str, str, float], ...]], ...] = (
    (
        "ecarts_unicite_id.geojson",
        "Unicite des identifiants",
        "Identifiants dupliques dans les fichiers RPD_*.geojson",
        _COLONNES_UNICITE_ID,
    ),
    (
        "ecarts_valeur_xsd.geojson",
        "Conformite des valeurs XSD",
        "Valeurs non conformes aux listes autorisees du modele RecoStaR",
        _COLONNES_VALEUR_XSD,
    ),
)


# --------------------------------------------------------------------------- #
# Styles du rapport
# --------------------------------------------------------------------------- #


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
    }


# --------------------------------------------------------------------------- #
# Chargement des resultats
# --------------------------------------------------------------------------- #


def _charger_features_geojson(chemin: str) -> list[dict[str, Any]] | None:
    """Charge les features d'un fichier GeoJSON d'ecarts.

    Retourne None si le fichier est absent.
    """
    if not os.path.isfile(chemin):
        return None
    with open(chemin, "r", encoding="utf-8") as fichier:
        donnees = json.load(fichier)
    return donnees.get("features", [])


def collecter_resultats_controles(
    repertoire: str,
) -> list[dict[str, Any]]:
    """Collecte les resultats de chaque controle depuis les fichiers d'ecarts.

    Parcourt les fichiers d'ecarts connus et retourne une liste de
    dictionnaires avec le nom du controle, les features chargees,
    le nombre d'anomalies et le statut de disponibilite.
    """
    resultats: list[dict[str, Any]] = []

    for nom_fichier, label, description, colonnes in CONTROLES:
        chemin = os.path.join(repertoire, nom_fichier)
        features = _charger_features_geojson(chemin)

        nb_anomalies = len(features) if features is not None else 0

        resultats.append(
            {
                "label": label,
                "description": description,
                "fichier": nom_fichier,
                "colonnes": colonnes,
                "features": features if features is not None else [],
                "nombre_anomalies": nb_anomalies,
                "disponible": features is not None,
            }
        )

    return resultats


# --------------------------------------------------------------------------- #
# Construction du tableau de synthese
# --------------------------------------------------------------------------- #


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


def _construire_synthese(
    styles: dict[str, ParagraphStyle],
    resultats: list[dict[str, Any]],
) -> list[Any]:
    """Construit la section de synthese globale du rapport."""
    elements: list[Any] = []

    nb_controles = len(resultats)
    nb_disponibles = sum(1 for r in resultats if r["disponible"])
    nb_total_anomalies = sum(r["nombre_anomalies"] for r in resultats)
    nb_controles_ok = sum(
        1 for r in resultats if r["disponible"] and r["nombre_anomalies"] == 0
    )

    elements.append(
        Paragraph(
            f"Controles executes : <b>{nb_disponibles}</b> / {nb_controles}",
            styles["normal"],
        )
    )
    elements.append(
        Paragraph(
            f"Controles sans anomalie : <b>{nb_controles_ok}</b>",
            styles["normal"],
        )
    )
    elements.append(
        Paragraph(
            f"Nombre total d'anomalies : <b>{nb_total_anomalies}</b>",
            styles["normal"],
        )
    )
    elements.append(Spacer(1, 6 * mm))

    return elements


def _construire_tableau_detail(
    styles: dict[str, ParagraphStyle],
    resultats: list[dict[str, Any]],
) -> list[Any]:
    """Construit le tableau recapitulatif des resultats par controle."""
    elements: list[Any] = []
    elements.append(Paragraph("Recapitulatif par controle", styles["sous_titre"]))

    donnees: list[list[Any]] = [
        ["Controle", "Description", "Anomalies", "Statut", "Fichier"]
    ]

    style_cellule = styles["cellule"]

    for resultat in resultats:
        if resultat["disponible"]:
            nb = resultat["nombre_anomalies"]
            statut = "OK" if nb == 0 else "Ecarts detectes"
        else:
            nb = "-"
            statut = "Non execute"

        donnees.append(
            [
                Paragraph(resultat["label"], style_cellule),
                Paragraph(resultat["description"], style_cellule),
                str(nb),
                statut,
                Paragraph(resultat["fichier"], style_cellule),
            ]
        )

    largeurs = [3.5 * cm, 6.0 * cm, 2.0 * cm, 2.5 * cm, 4.5 * cm]
    tableau = Table(donnees, colWidths=largeurs)
    tableau.setStyle(_style_tableau())
    elements.append(tableau)

    return elements


# --------------------------------------------------------------------------- #
# Detail des entites en ecart
# --------------------------------------------------------------------------- #


def _construire_tableau_entites(
    style_cellule: ParagraphStyle,
    features: list[dict[str, Any]],
    colonnes: tuple[tuple[str, str, float], ...],
) -> Table:
    """Construit un tableau detaille des entites en ecart pour un controle.

    Les colonnes affichees sont definies par la configuration du controle.
    """
    en_tetes = [col[1] for col in colonnes]
    donnees: list[list[Any]] = [en_tetes]

    for feature in features:
        props = feature.get("properties") or {}
        ligne = [
            Paragraph(str(props.get(cle, "-")), style_cellule) for cle, _, _ in colonnes
        ]
        donnees.append(ligne)

    largeurs = [col[2] * cm for col in colonnes]
    tableau = Table(donnees, colWidths=largeurs)
    tableau.setStyle(_style_tableau())
    return tableau


def construire_sections_detail(
    styles: dict[str, ParagraphStyle],
    resultats: list[dict[str, Any]],
) -> list[Any]:
    """Construit les sections de detail des entites en ecart pour chaque controle."""
    elements: list[Any] = []
    style_cellule = styles["cellule"]

    for resultat in resultats:
        features = resultat["features"]
        if not features:
            continue

        label = resultat["label"]
        nb = resultat["nombre_anomalies"]
        elements.append(
            Paragraph(
                f"{label} ({nb} anomalie{'s' if nb > 1 else ''})", styles["sous_titre"]
            )
        )

        tableau = _construire_tableau_entites(
            style_cellule, features, resultat["colonnes"]
        )
        elements.append(tableau)
        elements.append(Spacer(1, 4 * mm))

    return elements


# --------------------------------------------------------------------------- #
# Generation du PDF
# --------------------------------------------------------------------------- #


def generer_rapport_pdf(
    repertoire: str,
    chemin_pdf: str,
) -> dict[str, Any]:
    """Genere le rapport PDF de synthese des controles GML.

    Retourne un dictionnaire avec le statut de la generation.
    """
    resultats = collecter_resultats_controles(repertoire)
    styles = _creer_styles()

    doc = SimpleDocTemplate(
        chemin_pdf,
        pagesize=A4,
        leftMargin=MARGE,
        rightMargin=MARGE,
        topMargin=MARGE,
        bottomMargin=MARGE,
    )

    elements: list[Any] = []

    # Titre
    elements.append(Paragraph("Rapport des controles GML", styles["titre"]))
    elements.append(Spacer(1, 6 * mm))

    # Synthese globale
    elements.append(Paragraph("Synthese", styles["sous_titre"]))
    elements.extend(_construire_synthese(styles, resultats))

    # Tableau recapitulatif par controle
    elements.extend(_construire_tableau_detail(styles, resultats))

    # Detail des entites en ecart par controle
    elements.extend(construire_sections_detail(styles, resultats))

    doc.build(elements)

    nb_total = sum(r["nombre_anomalies"] for r in resultats)
    nb_disponibles = sum(1 for r in resultats if r["disponible"])

    return {
        "succes": True,
        "chemin_pdf": chemin_pdf,
        "controles_disponibles": nb_disponibles,
        "nombre_total_anomalies": nb_total,
    }


# --------------------------------------------------------------------------- #
# Point d'entree CLI
# --------------------------------------------------------------------------- #


def executer_rapport_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute la generation du rapport PDF en mode CLI.

    Lit les fichiers d'ecarts dans le repertoire et genere le PDF.
    """
    if not os.path.isdir(repertoire):
        return {"succes": False, "erreur": f"Repertoire introuvable : {repertoire}"}

    dossier_sortie = sortie if sortie is not None else repertoire
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_pdf = os.path.join(dossier_sortie, FICHIER_RAPPORT)

    return generer_rapport_pdf(repertoire, chemin_pdf)


def main() -> None:
    """Point d'entree CLI de la generation du rapport PDF."""
    parseur = argparse.ArgumentParser(
        description="Generation du rapport PDF des controles GML"
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant les fichiers d'ecarts GeoJSON",
    )
    parseur.add_argument(
        "--sortie",
        default=None,
        help="Repertoire de sortie (defaut : meme repertoire que l'entree)",
    )
    arguments = parseur.parse_args()

    resultat = executer_rapport_cli(arguments.repertoire, arguments.sortie)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
