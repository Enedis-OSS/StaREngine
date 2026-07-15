"""
Rapport PDF de synthese des controles RecoStaR (ReportLab).

Produit un document destine a etre transmis en l'etat : une page de synthese
donnant le statut de chaque famille et la ventilation des anomalies par
priorite, puis une section detaillee par famille listant chaque controle.

Ce module ne connait que le modele normalise de synthese_controles : il ignore
le format des rapports de pipeline. Toute famille ajoutee au registre y apparait
sans modification de ce module.

Polices : Helvetica (police standard PDF, encodage WinAnsi) — les accents des
libelles francais sont rendus sans embarquer de police externe.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from synthese_controles import (
    LIBELLES_PRIORITES,
    ORDRE_PRIORITES,
    PRIORITE_BLOQUANT,
    PRIORITE_INFORMATION,
    PRIORITE_MAJEUR,
    PRIORITE_MINEUR,
    STATUT_CONFORME,
    STATUT_INCOMPLET,
    STATUT_NON_CONFORME,
    ResultatFamille,
    priorites_presentes,
)

# --- Palette -----------------------------------------------------------------
#
# Deux teintes de reference definissent l'identite du rapport :
#   - principale : bleu, teinte 240° (#F6F6FE) ;
#   - secondaire : vert, teinte  80° (#F7FBEF).
#
# A 98 % et 96 % de luminosite, ces teintes ne peuvent porter que du texte
# fonce : elles servent de fonds. Les couleurs structurantes (bandeau, titres,
# filets) sont derivees des memes teintes, afin que le document lise bleu et
# vert dans son ensemble et non seulement dans ses aplats.
#
# Tous les couples texte/fond ci-dessous depassent le seuil WCAG AA (4.5:1).

# Fonds : teintes de reference, telles que fournies.
FOND_PRINCIPAL = colors.HexColor("#F6F6FE")  # bleu 240°, luminosite 98 %
FOND_SECONDAIRE = colors.HexColor("#F7FBEF")  # vert  80°, luminosite 96 %

# Couleurs structurantes, derivees des teintes de reference.
BLEU_NUIT = colors.HexColor("#18184E")  # teinte 240° — bandeau, titres (16.4:1 sur blanc)
BLEU = colors.HexColor("#3939AC")  # teinte 240° — filets, codes de controle
VERT = colors.HexColor("#56741B")  # teinte  80° — statut Conforme (5.1:1 sur fond secondaire)

# Couleurs semantiques : conservees hors de la charte, leur signification
# (alerte, avertissement) prime sur l'identite visuelle.
ROUGE = colors.HexColor("#C0392B")
ORANGE = colors.HexColor("#D97706")
JAUNE = colors.HexColor("#B7950B")

GRIS_TEXTE = colors.HexColor("#374151")
GRIS_DOUX = colors.HexColor("#6B7280")
GRIS_BORDURE = colors.HexColor("#DDDDEA")
BLANC = colors.white

# Couleur associee a chaque statut et a chaque priorite.
COULEURS_STATUT: dict[str, colors.Color] = {
    STATUT_CONFORME: VERT,
    STATUT_NON_CONFORME: ROUGE,
    STATUT_INCOMPLET: ORANGE,
}
COULEURS_PRIORITE: dict[str, colors.Color] = {
    PRIORITE_BLOQUANT: ROUGE,
    PRIORITE_MAJEUR: ORANGE,
    PRIORITE_MINEUR: JAUNE,
    PRIORITE_INFORMATION: BLEU,
}

# --- Mise en page -------------------------------------------------------------

MARGE: float = 16 * mm
HAUTEUR_BANDEAU: float = 26 * mm
POLICE: str = "Helvetica"
POLICE_GRASSE: str = "Helvetica-Bold"

TITRE_DOCUMENT: str = "Rapport de contrôle RecoStaR"


def _styles() -> dict[str, ParagraphStyle]:
    """Construit les styles de paragraphe du document."""
    return {
        "titre_section": ParagraphStyle(
            "titre_section",
            fontName=POLICE_GRASSE,
            fontSize=15,
            textColor=BLEU_NUIT,
            spaceAfter=2 * mm,
            alignment=TA_LEFT,
        ),
        "sous_titre": ParagraphStyle(
            "sous_titre",
            fontName=POLICE_GRASSE,
            fontSize=10.5,
            textColor=BLEU_NUIT,
            spaceBefore=3 * mm,
            spaceAfter=1.5 * mm,
        ),
        "corps": ParagraphStyle(
            "corps",
            fontName=POLICE,
            fontSize=9,
            textColor=GRIS_TEXTE,
            leading=12,
        ),
        "note": ParagraphStyle(
            "note",
            fontName=POLICE,
            fontSize=8,
            textColor=GRIS_DOUX,
            leading=10.5,
        ),
        "cellule": ParagraphStyle(
            "cellule",
            fontName=POLICE,
            fontSize=8.5,
            textColor=GRIS_TEXTE,
            leading=11,
        ),
    }


def _filet(largeur: float, couleur: colors.Color = BLEU) -> HRFlowable:
    """Construit le filet colore separant le titre d'une section de son contenu.

    HRFlowable est le filet horizontal fourni par ReportLab : aucun Flowable
    specifique n'est derive. lineCap 'butt' donne des extremites droites, alignees
    sur les bords des tableaux.
    """
    return HRFlowable(
        width=largeur,
        thickness=2.2,
        color=couleur,
        lineCap="butt",
        spaceBefore=0,
        spaceAfter=0,
        hAlign="LEFT",
    )


# --- Bandeau et pied de page ---------------------------------------------------


def _dessiner_bandeau(canvas: Canvas, doc: SimpleDocTemplate) -> None:
    """Dessine le bandeau de titre et le pied de page sur chaque page."""
    largeur, hauteur = A4

    canvas.saveState()
    canvas.setFillColor(BLEU_NUIT)
    canvas.rect(0, hauteur - HAUTEUR_BANDEAU, largeur, HAUTEUR_BANDEAU, stroke=0, fill=1)
    canvas.setFillColor(BLEU)
    canvas.rect(0, hauteur - HAUTEUR_BANDEAU, largeur, 1.6 * mm, stroke=0, fill=1)

    canvas.setFillColor(BLANC)
    canvas.setFont(POLICE_GRASSE, 14)
    canvas.drawString(MARGE, hauteur - 15 * mm, TITRE_DOCUMENT)
    canvas.setFont(POLICE, 8.5)
    # Bleu clair de la meme teinte (240°) que le fond principal : la date reste
    # lisible sur le bandeau sans concurrencer le titre.
    canvas.setFillColor(colors.HexColor("#B8B8DE"))
    canvas.drawRightString(largeur - MARGE, hauteur - 15 * mm, datetime.now().strftime("%d/%m/%Y à %H:%M"))

    canvas.setStrokeColor(GRIS_BORDURE)
    canvas.setLineWidth(0.5)
    canvas.line(MARGE, 13 * mm, largeur - MARGE, 13 * mm)
    canvas.setFont(POLICE, 7.5)
    canvas.setFillColor(GRIS_DOUX)
    canvas.drawString(MARGE, 9 * mm, TITRE_DOCUMENT)
    canvas.drawRightString(largeur - MARGE, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


# --- Composants de contenu -----------------------------------------------------


def _pastille_statut(statut: str) -> Table:
    """Construit la pastille coloree d'un statut."""
    couleur = COULEURS_STATUT.get(statut, GRIS_DOUX)
    pastille = Table([[statut.upper()]], colWidths=[32 * mm], rowHeights=[6.5 * mm])
    pastille.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), couleur),
                ("TEXTCOLOR", (0, 0), (-1, -1), BLANC),
                ("FONTNAME", (0, 0), (-1, -1), POLICE_GRASSE),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return pastille


def _encadre_global(synthese: dict[str, Any], repertoire: Path, largeur: float) -> Table:
    """Construit l'encadre de synthese globale en tete de rapport."""
    statut = str(synthese["statut_global"])
    couleur = COULEURS_STATUT.get(statut, GRIS_DOUX)
    styles = _styles()

    gauche = [
        Paragraph(f"<b>Jeu de données</b><br/>{repertoire.name}", styles["corps"]),
        Spacer(1, 2 * mm),
        Paragraph(
            f"{synthese['nombre_familles_executees']} famille(s) · "
            f"{synthese['nombre_controles_executes']} contrôle(s) exécuté(s) · "
            f"{synthese['nombre_anomalies_total']} anomalie(s)",
            styles["note"],
        ),
    ]
    droite = Table([[statut.upper()]], colWidths=[46 * mm], rowHeights=[14 * mm])
    droite.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), couleur),
                ("TEXTCOLOR", (0, 0), (-1, -1), BLANC),
                ("FONTNAME", (0, 0), (-1, -1), POLICE_GRASSE),
                ("FONTSIZE", (0, 0), (-1, -1), 12),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )

    encadre = Table([[gauche, droite]], colWidths=[largeur - 46 * mm, 46 * mm])
    encadre.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), FOND_PRINCIPAL),
                ("BOX", (0, 0), (0, 0), 0.5, GRIS_BORDURE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (0, 0), 5 * mm),
                ("TOPPADDING", (0, 0), (0, 0), 4 * mm),
                ("BOTTOMPADDING", (0, 0), (0, 0), 4 * mm),
                ("LEFTPADDING", (1, 0), (1, 0), 0),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
            ]
        )
    )
    return encadre


def _entetes_synthese(priorites: tuple[str, ...]) -> list[str]:
    """Construit la ligne d'en-tete du tableau de synthese."""
    return ["Famille", "Statut", "Contrôles", "Anomalies", *(LIBELLES_PRIORITES[p] for p in priorites)]


def _ligne_synthese(famille: ResultatFamille, priorites: tuple[str, ...]) -> list[str]:
    """Construit la ligne de synthese d'une famille."""
    if not famille.execute:
        return [famille.libelle, famille.statut, "—", "—", *("—" for _ in priorites)]
    ventilation = famille.anomalies_par_priorite
    return [
        famille.libelle,
        famille.statut,
        str(famille.nombre_controles),
        str(famille.nombre_anomalies),
        *(str(ventilation.get(p, 0)) for p in priorites),
    ]


def _style_tableau_synthese(familles: tuple[ResultatFamille, ...], nb_colonnes: int) -> TableStyle:
    """Construit le style du tableau de synthese, avec statuts colores."""
    commandes: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), BLEU_NUIT),
        ("TEXTCOLOR", (0, 0), (-1, 0), BLANC),
        ("FONTNAME", (0, 0), (-1, 0), POLICE_GRASSE),
        ("FONTNAME", (0, 1), (0, -1), POLICE_GRASSE),
        ("FONTNAME", (1, 1), (-1, -1), POLICE),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TEXTCOLOR", (0, 1), (0, -1), BLEU_NUIT),
        ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, GRIS_BORDURE),
        ("BOX", (0, 0), (-1, -1), 0.6, GRIS_BORDURE),
    ]
    for indice, famille in enumerate(familles, start=1):
        if indice % 2 == 0:
            commandes.append(("BACKGROUND", (0, indice), (-1, indice), FOND_PRINCIPAL))
        couleur = COULEURS_STATUT.get(famille.statut, GRIS_DOUX)
        commandes.append(("TEXTCOLOR", (1, indice), (1, indice), couleur))
        commandes.append(("FONTNAME", (1, indice), (1, indice), POLICE_GRASSE))
        # Met en evidence la colonne bloquante lorsqu'elle est alimentee
        if famille.execute and famille.anomalies_par_priorite.get(PRIORITE_BLOQUANT, 0) > 0:
            commandes.append(("TEXTCOLOR", (4, indice), (4, indice), ROUGE))
            commandes.append(("FONTNAME", (4, indice), (4, indice), POLICE_GRASSE))
    _ = nb_colonnes
    return TableStyle(commandes)


def _tableau_synthese(familles: tuple[ResultatFamille, ...], largeur: float) -> Table:
    """Construit le tableau de synthese par famille."""
    priorites = priorites_presentes(familles)
    donnees = [_entetes_synthese(priorites)]
    donnees.extend(_ligne_synthese(f, priorites) for f in familles)

    largeur_fixe = 28 * mm + 22 * mm + 24 * mm + len(priorites) * 24 * mm
    colonnes = [largeur - largeur_fixe, 28 * mm, 22 * mm, 24 * mm, *(24 * mm for _ in priorites)]
    tableau = Table(donnees, colWidths=colonnes, repeatRows=1)
    tableau.setStyle(_style_tableau_synthese(familles, len(donnees[0])))
    return tableau


def _lignes_detail(famille: ResultatFamille, styles: dict[str, ParagraphStyle]) -> list[list[Any]]:
    """Construit les lignes du tableau detaille d'une famille."""
    lignes: list[list[Any]] = [["Code", "Contrôle", "Anomalies", "Priorité"]]
    for controle in famille.controles:
        if not controle.succes:
            priorite = "—"
            anomalies = "échec"
        else:
            ventilation = controle.anomalies_par_priorite
            anomalies = str(controle.nombre_anomalies)
            priorite = (
                " · ".join(f"{LIBELLES_PRIORITES.get(p, p)} ({n})" for p, n in _trier(ventilation))
                if ventilation
                else "—"
            )
        lignes.append(
            [
                controle.code,
                Paragraph(controle.libelle, styles["cellule"]),
                anomalies,
                Paragraph(priorite, styles["cellule"]),
            ]
        )
    return lignes


def _trier(ventilation: dict[str, int]) -> list[tuple[str, int]]:
    """Trie une ventilation par gravite decroissante."""
    return [(p, ventilation[p]) for p in ORDRE_PRIORITES if p in ventilation]


def _style_tableau_detail(famille: ResultatFamille) -> TableStyle:
    """Construit le style du tableau detaille d'une famille."""
    commandes: list[tuple[Any, ...]] = [
        # Fond secondaire (vert) : distingue les tableaux de detail du tableau
        # de synthese, dont l'en-tete est en bleu nuit.
        ("BACKGROUND", (0, 0), (-1, 0), FOND_SECONDAIRE),
        ("TEXTCOLOR", (0, 0), (-1, 0), BLEU_NUIT),
        ("FONTNAME", (0, 0), (-1, 0), POLICE_GRASSE),
        ("FONTNAME", (0, 1), (0, -1), POLICE_GRASSE),
        ("FONTNAME", (2, 1), (2, -1), POLICE),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 1), (0, -1), BLEU),
        ("ALIGN", (2, 0), (2, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2 * mm),
        ("LINEBELOW", (0, 0), (-1, -2), 0.35, GRIS_BORDURE),
        ("BOX", (0, 0), (-1, -1), 0.6, GRIS_BORDURE),
    ]
    for indice, controle in enumerate(famille.controles, start=1):
        if not controle.succes:
            commandes.append(("TEXTCOLOR", (2, indice), (2, indice), ORANGE))
        elif controle.anomalies_par_priorite.get(PRIORITE_BLOQUANT, 0) > 0:
            commandes.append(("TEXTCOLOR", (2, indice), (2, indice), ROUGE))
            commandes.append(("FONTNAME", (2, indice), (2, indice), POLICE_GRASSE))
        elif controle.nombre_anomalies > 0:
            commandes.append(("TEXTCOLOR", (2, indice), (2, indice), BLEU))
    return TableStyle(commandes)


def _section_famille(
    famille: ResultatFamille,
    largeur: float,
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    """Construit la section detaillee d'une famille."""
    entete = Table(
        [[Paragraph(famille.libelle, styles["titre_section"]), _pastille_statut(famille.statut)]],
        colWidths=[largeur - 32 * mm, 32 * mm],
    )
    entete.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1 * mm),
            ]
        )
    )
    elements: list[Any] = [entete, _filet(largeur), Spacer(1, 3 * mm)]

    if not famille.execute:
        elements.append(Paragraph(f"Famille non exécutée — {famille.motif or 'motif non précisé'}", styles["note"]))
        elements.append(Spacer(1, 6 * mm))
        return elements

    tableau = Table(
        _lignes_detail(famille, styles), colWidths=[16 * mm, largeur - 74 * mm, 22 * mm, 36 * mm], repeatRows=1
    )
    tableau.setStyle(_style_tableau_detail(famille))
    elements.append(tableau)

    # Le motif de chaque echec est restitue : sans lui, le statut « Incomplet »
    # resterait inexplique pour le lecteur du rapport.
    for controle in famille.controles:
        if controle.succes:
            continue
        elements.append(Spacer(1, 1.5 * mm))
        elements.append(
            Paragraph(
                f"<b>{controle.code}</b> n'a pas pu s'exécuter — {controle.erreur}",
                styles["note"],
            )
        )
    elements.append(Spacer(1, 7 * mm))
    return elements


# --- Assemblage du document ----------------------------------------------------


def _page_synthese(
    familles: tuple[ResultatFamille, ...],
    synthese: dict[str, Any],
    repertoire: Path,
    largeur: float,
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    """Construit les elements de la page de synthese."""
    elements: list[Any] = [
        Paragraph("Synthèse des contrôles", styles["titre_section"]),
        _filet(largeur),
        Spacer(1, 4 * mm),
        _encadre_global(synthese, repertoire, largeur),
        Spacer(1, 6 * mm),
        _tableau_synthese(familles, largeur),
        Spacer(1, 4 * mm),
    ]

    for message in _messages_synthese(familles, synthese):
        elements.append(Paragraph(message, styles["corps"]))
        elements.append(Spacer(1, 1.5 * mm))

    elements.append(Spacer(1, 1 * mm))
    elements.append(
        Paragraph(
            "Les anomalies de priorité « Information » sont comptabilisées et détaillées, mais ne "
            "déclassent pas le statut. Le statut « Incomplet » signale qu'aucune anomalie bloquante "
            "n'a été détectée mais qu'au moins un contrôle n'a pas pu s'exécuter : la conformité "
            "n'est alors pas vérifiable (voir le motif dans le détail de la famille).",
            styles["note"],
        )
    )
    return elements


def _libelles(familles: tuple[ResultatFamille, ...], cles: Any) -> str:
    """Retourne les libelles des familles designees par leurs cles."""
    ensemble = set(cles)
    return ", ".join(f.libelle for f in familles if f.cle in ensemble)


def _messages_synthese(familles: tuple[ResultatFamille, ...], synthese: dict[str, Any]) -> list[str]:
    """Construit les phrases de synthese placees sous le tableau."""
    messages: list[str] = []
    non_conformes = synthese["familles_non_conformes"]
    incompletes = synthese.get("familles_incompletes", ())

    if non_conformes:
        messages.append(
            f"Famille(s) présentant des anomalies bloquantes : <b>{_libelles(familles, non_conformes)}</b>."
        )
    else:
        messages.append("Aucune anomalie bloquante détectée sur les familles exécutées.")

    if incompletes:
        messages.append(f"Famille(s) au contrôle incomplet : <b>{_libelles(familles, incompletes)}</b>.")

    nb_echecs = synthese.get("nombre_controles_en_echec", 0)
    if nb_echecs:
        messages.append(f"{nb_echecs} contrôle(s) n'ont pas pu s'exécuter, faute de donnée d'entrée ou de paramètre.")
    return messages


def generer_rapport_pdf(
    familles: tuple[ResultatFamille, ...],
    synthese: dict[str, Any],
    chemin: Path,
    repertoire: Path,
) -> Path:
    """Genere le rapport PDF de synthese et retourne son chemin.

    Le document comporte une page de synthese puis une section par famille, dans
    l'ordre du registre. Les sections sont maintenues solidaires (KeepTogether)
    afin qu'un tableau ne soit pas coupe entre deux pages.
    """
    document = SimpleDocTemplate(
        str(chemin),
        pagesize=A4,
        leftMargin=MARGE,
        rightMargin=MARGE,
        topMargin=HAUTEUR_BANDEAU + 8 * mm,
        bottomMargin=18 * mm,
        title=TITRE_DOCUMENT,
        author="RecoStaR",
        subject=f"Contrôles du jeu de données {repertoire.name}",
    )
    largeur = document.width
    styles = _styles()

    elements: list[Any] = _page_synthese(familles, synthese, repertoire, largeur, styles)
    elements.append(PageBreak())
    elements.append(Paragraph("Détail par famille", styles["titre_section"]))
    elements.append(_filet(largeur))
    elements.append(Spacer(1, 5 * mm))
    for famille in familles:
        elements.append(KeepTogether(_section_famille(famille, largeur, styles)))

    document.build(elements, onFirstPage=_dessiner_bandeau, onLaterPages=_dessiner_bandeau)
    return chemin
