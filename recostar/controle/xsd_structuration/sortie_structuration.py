#!/usr/bin/env python3
"""
Sortie JSON harmonisee de la famille de structuration.

Les six controles de la famille produisent chacun leur rapport, et six formes
d'erreur differentes : `ErreurOrdre` nomme sa regle `type_erreur`, `ErreurEntete`
l'appelle `code`, `ErreurMetier` `regle` ; l'entete et la validation XSD native
ne portent meme pas de `gml_id`. Utile au diagnostic d'un controle isole, cette
diversite interdit toute lecture d'ensemble.

Ce module ramene la famille a **un fichier et huit champs**, les memes que ceux
des familles GeoJSON (cf. `fonctions_communes.sortie_famille`) :

    CODE              code du verificateur (« E-1108 »)
    CRITICITE         niveau de l'anomalie
    LIBELLE           code de la regle enfreinte
    FAMILLE_CONTROLE  « structuration »
    DESIGNATION_RPD   type de l'objet RPD en anomalie
    ID_GML            gml:id de l'objet en anomalie
    ID_GML_ASSOCIE    vide : la structuration ne met qu'une entite en cause
    INFO              message, augmente du detail technique

Pourquoi la nomenclature est redeclaree ici
-------------------------------------------
Les modules de `xsd_structuration/` ne dependent pas du paquet parent : ils
s'importent a plat et restent executables seuls. C'est le parti deja retenu par
`priorites_structuration` pour l'echelle de priorites et par
`codes_verificateur_xsd` pour la table des codes. Les huit noms de champ sont
donc redeclares plutot qu'importes, et un test les confronte a ceux du paquet
parent : toute divergence entre les deux nomenclatures est ainsi visible.

Le format reste du JSON, non du GeoJSON : un GML n'a pas de geometrie a porter
au niveau ou ces controles operent.
"""

import json
import os
from collections.abc import Iterable, Mapping
from typing import Any

from recostar.controle.xsd_structuration.codes_verificateur_xsd import (
    rang_depuis_code_controle,
    resoudre_code_erreur_xsd,
)
from recostar.controle.xsd_structuration.priorites_structuration import (
    PRIORITE_PAR_DEFAUT,
    compter_bloquantes,
    statut_conformite,
)

# ---------------------------------------------------------------------------
# Nomenclature de sortie (miroir de fonctions_communes.sortie_famille)
# ---------------------------------------------------------------------------

CHAMP_CODE: str = "CODE"
CHAMP_CRITICITE: str = "CRITICITE"
CHAMP_LIBELLE: str = "LIBELLE"
CHAMP_FAMILLE_CONTROLE: str = "FAMILLE_CONTROLE"
CHAMP_DESIGNATION_RPD: str = "DESIGNATION_RPD"
CHAMP_ID_GML: str = "ID_GML"
CHAMP_ID_GML_ASSOCIE: str = "ID_GML_ASSOCIE"
CHAMP_INFO: str = "INFO"

# Ordre d'apparition dans le fichier produit.
CHAMPS_SORTIE: tuple[str, ...] = (
    CHAMP_CODE,
    CHAMP_CRITICITE,
    CHAMP_LIBELLE,
    CHAMP_FAMILLE_CONTROLE,
    CHAMP_DESIGNATION_RPD,
    CHAMP_ID_GML,
    CHAMP_ID_GML_ASSOCIE,
    CHAMP_INFO,
)

# Cle de la famille, reportee dans FAMILLE_CONTROLE. Identique a celle declaree
# par `familles_controle.FAMILLES`.
FAMILLE: str = "structuration"

# Suffixe du fichier unique produit, aligne sur la convention des rapports par
# controle (« _controle_e0013.json »).
SUFFIXE_SORTIE: str = "_controle_structuration.json"

# Champs sous lesquels une erreur nomme la regle enfreinte, par ordre de
# preference : les six classes d'erreur de la famille n'emploient pas le meme.
CHAMPS_REGLE: tuple[str, ...] = ("type_erreur", "code", "regle")

# Champ portant le type de l'objet RPD en anomalie.
CHAMP_TYPE_RPD: str = "type_rpd"

# Champ portant l'identifiant GML de l'objet en anomalie.
CHAMP_GML_ID: str = "gml_id"

# Champ portant le message redige par le controle.
CHAMP_MESSAGE: str = "message"

# Champ portant la priorite, calculee par chaque classe d'erreur.
CHAMP_PRIORITE: str = "priorite"

# Champs deja rendus par les sept premieres colonnes : ils n'ont pas a etre
# repetes dans INFO. `severite` en fait partie, la famille etant mono-severite.
_CHAMPS_CONSOMMES: frozenset[str] = frozenset(
    {*CHAMPS_REGLE, CHAMP_TYPE_RPD, CHAMP_GML_ID, CHAMP_MESSAGE, CHAMP_PRIORITE, "severite"}
)

# Valeur d'un gml:id absent, telle que les moteurs l'ecrivent.
_ID_ABSENT: str = "<sans id>"


def code_regle_erreur(erreur: Mapping[str, Any]) -> str | None:
    """Retourne le code de la regle enfreinte, quel que soit son nom de champ."""
    for champ in CHAMPS_REGLE:
        valeur = erreur.get(champ)
        if valeur:
            return str(valeur)
    return None


def _identifiant(erreur: Mapping[str, Any]) -> str:
    """Retourne le gml:id de l'objet en anomalie, ou une chaine vide.

    Les erreurs d'en-tete et de validation XSD native portent sur le fichier,
    non sur un objet : elles n'ont pas d'identifiant. Le marqueur « <sans id> »
    des moteurs est ramene a la meme chaine vide, pour n'avoir qu'un cas.
    """
    valeur = erreur.get(CHAMP_GML_ID)
    if not valeur or valeur == _ID_ABSENT:
        return ""
    return str(valeur)


def construire_info(erreur: Mapping[str, Any]) -> str:
    """Redige INFO : le message du controle, augmente de son detail technique.

    Les champs propres a chaque classe d'erreur (position, element attendu,
    ligne et colonne lxml, nombre de positions...) sont repris sous la forme
    « nom : valeur ». Sans eux, l'anomalie serait nommee mais pas situee.
    """
    message = erreur.get(CHAMP_MESSAGE)
    details = [
        f"{champ} : {valeur}"
        for champ, valeur in erreur.items()
        if champ not in _CHAMPS_CONSOMMES and valeur is not None and valeur != ""
    ]
    texte = str(message) if message else ""
    if not details:
        return texte
    return f"{texte} {', '.join(details)}".strip()


def harmoniser_erreur(erreur: Mapping[str, Any], code_controle: str) -> dict[str, Any]:
    """Convertit une erreur de structuration vers la nomenclature de sortie.

    `code_controle` (« E0013 ») donne le rang du controle, seule maille a
    laquelle le code du verificateur se resout : une meme regle n'a pas le meme
    code selon le controle qui l'emet.
    """
    rang = rang_depuis_code_controle(code_controle)
    code_regle = code_regle_erreur(erreur)
    code_erreur = resoudre_code_erreur_xsd(rang, code_regle) if rang is not None else None
    return {
        # A defaut de code du verificateur, le code du controle identifie
        # l'anomalie : la colonne ne doit jamais rester vide.
        CHAMP_CODE: code_erreur or code_controle,
        CHAMP_CRITICITE: erreur.get(CHAMP_PRIORITE) or PRIORITE_PAR_DEFAUT,
        CHAMP_LIBELLE: code_regle,
        CHAMP_FAMILLE_CONTROLE: FAMILLE,
        CHAMP_DESIGNATION_RPD: str(erreur.get(CHAMP_TYPE_RPD) or ""),
        CHAMP_ID_GML: _identifiant(erreur),
        # La structuration ne met jamais deux entites en cause : le champ existe
        # pour que la sortie soit identique a celle des familles GeoJSON.
        CHAMP_ID_GML_ASSOCIE: "",
        CHAMP_INFO: construire_info(erreur),
    }


def _code_depuis_type_controle(type_controle: Any) -> str:
    """Extrait le code affichable du `type_controle` d'un rapport.

    « E0013_ENTETE » donne « E0013 » : le suffixe nomme le controle, le prefixe
    l'identifie.
    """
    return str(type_controle or "").split("_", 1)[0]


def _lire_rapport(chemin: str) -> dict[str, Any] | None:
    """Lit un rapport de controle, ou None s'il est illisible.

    Un rapport illisible ne doit pas interrompre l'agregation : les anomalies
    des autres controles de la famille restent exploitables.
    """
    try:
        with open(chemin, encoding="utf-8") as fichier:
            return json.load(fichier)
    except (OSError, json.JSONDecodeError):
        return None


def agreger_rapports_structuration(
    chemins: Iterable[str | None],
    chemin_gml: str,
    dossier_sortie: str,
    entete: Mapping[str, Any] | None = None,
    supprimer_sources: bool = True,
) -> dict[str, Any]:
    """Fusionne les rapports de la famille en un JSON unique.

    `chemins` recoit les rapports ecrits par les controles, dans leur ordre
    d'execution ; les valeurs None (controle en echec) sont ignorees. `entete`
    complete la synthese du fichier produit avec ce que le pipeline sait deja
    (version controlee, conformite globale).

    Les rapports sources sont supprimes une fois fusionnes : la famille ne doit
    laisser qu'un fichier. `supprimer_sources` a False les conserve.

    Retourne un compte rendu : chemin ecrit, nombre d'anomalies, rapports
    agreges.
    """
    anomalies: list[dict[str, Any]] = []
    sources: list[str] = []

    for chemin in chemins:
        if not chemin or not os.path.isfile(chemin):
            continue
        sources.append(chemin)
        rapport = _lire_rapport(chemin)
        if rapport is None:
            continue
        code_controle = _code_depuis_type_controle(rapport.get("type_controle"))
        anomalies.extend(harmoniser_erreur(erreur, code_controle) for erreur in rapport.get("erreurs") or ())

    chemin_ecrit = _ecrire(anomalies, chemin_gml, dossier_sortie, entete)

    if supprimer_sources:
        _supprimer(sources, sauf=chemin_ecrit)

    return {
        "sortie": chemin_ecrit,
        "nombre_anomalies": len(anomalies),
        "rapports_agreges": len(sources),
    }


def _ventiler(anomalies: list[dict[str, Any]]) -> dict[str, int]:
    """Ventile les anomalies agregees par criticite."""
    ventilation: dict[str, int] = {}
    for anomalie in anomalies:
        criticite = str(anomalie[CHAMP_CRITICITE])
        ventilation[criticite] = ventilation.get(criticite, 0) + 1
    return ventilation


def nom_fichier_sortie(chemin_gml: str) -> str:
    """Nom du fichier unique de la famille, derive de celui du GML controle."""
    return os.path.splitext(os.path.basename(chemin_gml))[0] + SUFFIXE_SORTIE


def _ecrire(
    anomalies: list[dict[str, Any]],
    chemin_gml: str,
    dossier_sortie: str,
    entete: Mapping[str, Any] | None,
) -> str:
    """Ecrit le fichier unique de la famille.

    Contrairement aux familles GeoJSON, le fichier est ecrit meme sans anomalie :
    la structuration rend toujours un verdict de conformite, qui est lui-meme
    l'information attendue.
    """
    ventilation = _ventiler(anomalies)
    rapport: dict[str, Any] = {
        "fichier": os.path.abspath(chemin_gml),
        "famille": FAMILLE,
        **(dict(entete) if entete else {}),
        "conformite": statut_conformite(ventilation),
        "nombre_anomalies": len(anomalies),
        "nombre_anomalies_bloquantes": compter_bloquantes(ventilation),
        "anomalies_par_criticite": ventilation,
        "anomalies": anomalies,
    }
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin = os.path.join(dossier_sortie, nom_fichier_sortie(chemin_gml))
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(rapport, fichier, ensure_ascii=False, indent=2)
    return chemin


def _supprimer(chemins: Iterable[str], sauf: str | None) -> None:
    """Supprime les rapports agreges, sans toucher au fichier produit."""
    reference = os.path.abspath(sauf) if sauf else None
    for chemin in chemins:
        if reference is not None and os.path.abspath(chemin) == reference:
            continue
        try:
            os.remove(chemin)
        except OSError:
            # Un fichier deja disparu n'est pas une erreur : l'agregation a
            # atteint son but.
            continue
