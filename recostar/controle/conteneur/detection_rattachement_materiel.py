"""
Moteur de detection du rattachement des boites de jonction a leur materiel.

Une boite de jonction ou de derivation abrite un materiel, et un seul. Le
verificateur en fait deux codes, selon le sens de l'ecart :

    E-7100  boite sans materiel associe                 niveau forte
    E-7101  boite avec plusieurs materiels associes      niveau forte

Les deux se lisent sur le meme decompte — le nombre de relations
`Ouvrage_Materiel` visant la boite — et sont exclusifs : une boite en a zero, un
ou plusieurs. Un seul parcours les releve tous deux.

Le GML source fait foi
----------------------
Le moteur lit le **GML d'entree**, et non les GeoJSON. La raison tient a la
conversion : `recostar_to_geojson` indexe les relations dans un dictionnaire
`ouvrage_id -> materiel_id`, par **affectation**. Une boite portant deux
relations `Ouvrage_Materiel` n'en conserve donc qu'une dans son `materiel_href`,
la seconde ecrasant la premiere.

E-7101 serait ainsi structurellement indetectable apres conversion : le defaut
qu'il nomme est precisement celui que la conversion efface. E-7100, lui, se
lirait sur l'absence du champ, mais les deux codes partagent un decompte : les
separer par leur source aurait fait diverger leurs perimetres.

Sans GML, le moteur ne peut rien conclure et les controles se declarent sans
objet plutot que de rendre un faux conforme. C'est le seul moteur du projet dans
ce cas : ailleurs, le repli GeoJSON reste exploitable.

Perimetre : les RPD_Jonction_Reco dont le TypeJonction designe une boite —
Derivation ou Jonction, cf. `TYPES_JONCTION_AVEC_MATERIEL` — et dont le Statut
vaut UnderCommissionning. Les ExtremiteReseau et les remontees aero-souterraines
n'abritent legitimement aucun materiel ; une jonction d'un autre statut n'est pas
encore posee. Meme perimetre que le catalogue de materiel et son controle de
rattachement.

Regle de gestion : une anomalie par boite fautive. Une boite portant trois
materiels porte **une** anomalie E-7101, non deux : c'est le rattachement qui est
a corriger, pas chacun des liens en trop — leur nombre est reporte a l'ecart.

Controles issus de ce moteur : e7100, e7101.

"""

import os
from collections import Counter
from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.ecarts import filtrer_par_type
from recostar.controle.fonctions_communes.geojson import (
    ProfilEcarts,
    compter_anomalies_par_type,
    ecrire_geojson_si_anomalies,
    normaliser_geojson_ecarts,
)
from recostar.controle.fonctions_communes.lecture_gml import (
    ATTR_GML_ID,
    charger_racine,
    href_enfant,
    parcourir_objets,
    positions_geometrie,
    texte_enfant,
)
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_STATUT,
    CHAMP_TYPE_JONCTION,
    FICHIER_JONCTION,
    STATUT_MISE_EN_SERVICE,
    TYPES_JONCTION_AVEC_MATERIEL,
)
from recostar.controle.fonctions_communes.resultats import rapport_sans_objet
from recostar.controle.fonctions_communes.source_gml import resoudre_chemin_gml

# Types d'objet GML lus par ce moteur.
TYPE_RPD_JONCTION: str = "RPD_Jonction_Reco"
TYPE_RELATION_MATERIEL: str = "Ouvrage_Materiel"

# Noms des enfants portant les deux bouts de la relation.
BALISE_OUVRAGE: str = "ouvrage"
BALISE_MATERIEL: str = "materiel"

# Types d'anomalie produits, un par sens d'ecart.
TYPE_SANS_MATERIEL: str = "boite_sans_materiel"
TYPE_MATERIELS_MULTIPLES: str = "boite_materiels_multiples"

# Nombre de materiels attendu par boite.
NB_MATERIELS_ATTENDU: int = 1

# Nombre minimal de coordonnees decrivant une position exploitable.
COORDONNEES_MINIMALES: int = 2

# Source lue, reportee au rapport. Le moteur n'en connait qu'une.
SOURCE_GML: str = "gml"


# ---------------------------------------------------------------------------
# Lecture du GML
# ---------------------------------------------------------------------------


def est_boite_a_controler(element: Any) -> bool:
    """Indique si une jonction GML entre dans le perimetre du controle.

    Deux conditions cumulatives : un TypeJonction designant une boite, et un
    Statut UnderCommissionning. Une ExtremiteReseau ou une remontee
    aero-souterraine n'abrite legitimement aucun materiel.
    """
    if texte_enfant(element, CHAMP_TYPE_JONCTION) not in TYPES_JONCTION_AVEC_MATERIEL:
        return False
    return texte_enfant(element, CHAMP_STATUT) == STATUT_MISE_EN_SERVICE


def _identifiant_cible(reference: str | None) -> str | None:
    """Normalise une reference `xlink:href` en identifiant confrontable.

    Le GML admet la forme fragmentee « #idXXXX » : le fragment designe un objet
    du meme document, et c'est son identifiant qu'il faut retenir.
    """
    if reference is None:
        return None
    return reference.lstrip("#").strip() or None


def compter_materiels_par_ouvrage(racine: Any) -> Counter[str]:
    """Compte les materiels **distincts** associes a chaque ouvrage.

    C'est ce decompte que le convertisseur perd : il indexe la relation par
    affectation, une boite a deux materiels n'en gardant qu'un. Le lire
    directement dans le GML est la seule facon de voir le defaut d'E-7101.

    Les couples (ouvrage, materiel) sont deduplique avant le comptage : deux
    lignes de jointure identiques decrivent **un** rattachement, non deux. Les
    compter separement ferait sortir en E-7101 une boite qui n'a qu'un materiel,
    alors que le defaut est un doublon de table de jointure — le code E-0012 du
    verificateur, qui n'est pas couvert a ce jour.

    Une relation dont l'un des deux bouts manque est ignoree : elle ne decrit
    aucun rattachement, et sa structure releve du controle de structuration E0110.
    """
    couples: set[tuple[str, str]] = set()
    for relation in parcourir_objets(racine, frozenset({TYPE_RELATION_MATERIEL})):
        ouvrage = _identifiant_cible(href_enfant(relation, BALISE_OUVRAGE))
        materiel = _identifiant_cible(href_enfant(relation, BALISE_MATERIEL))
        if ouvrage is not None and materiel is not None:
            couples.add((ouvrage, materiel))
    return Counter(ouvrage for ouvrage, _ in couples)


def lire_boites(racine: Any) -> list[dict[str, Any]]:
    """Lit les boites du perimetre et les rend avec leur position.

    Seuls l'identifiant, le type et la geometrie sont retenus : le reste de
    l'objet ne concerne aucune des deux regles.
    """
    boites: list[dict[str, Any]] = []
    for element in parcourir_objets(racine, frozenset({TYPE_RPD_JONCTION})):
        if not est_boite_a_controler(element):
            continue
        coordonnees = positions_geometrie(element)
        boites.append(
            {
                "id_jonction": element.get(ATTR_GML_ID),
                "type_jonction": texte_enfant(element, CHAMP_TYPE_JONCTION),
                "geometrie": (
                    {"type": "Point", "coordinates": coordonnees} if len(coordonnees) >= COORDONNEES_MINIMALES else None
                ),
            }
        )
    return boites


# ---------------------------------------------------------------------------
# Regle metier (fonction pure, testable sans I/O)
# ---------------------------------------------------------------------------


def classifier_boite(nombre_materiels: int) -> str | None:
    """Retourne le type d'anomalie d'une boite selon son nombre de materiels.

    Les deux regles sont exclusives et couvrent tout : une boite en a zero, un —
    le cas conforme — ou plusieurs.
    """
    if nombre_materiels == 0:
        return TYPE_SANS_MATERIEL
    if nombre_materiels > NB_MATERIELS_ATTENDU:
        return TYPE_MATERIELS_MULTIPLES
    return None


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def detecter_anomalies(boites: list[dict[str, Any]], decompte: Counter[str]) -> list[dict[str, Any]]:
    """Detecte les boites sans materiel ou a materiels multiples.

    Une anomalie par boite fautive : une boite portant trois materiels en porte
    une seule, leur nombre etant reporte a l'ecart.
    """
    classifier = classifier_boite  # alias local (boucle)
    anomalies: list[dict[str, Any]] = []
    for boite in boites:
        identifiant = boite["id_jonction"]
        nombre = decompte.get(identifiant, 0) if identifiant is not None else 0
        type_anomalie = classifier(nombre)
        if type_anomalie is None:
            continue
        anomalies.append({**boite, "type_anomalie": type_anomalie, "nombre_materiels": nombre})
    return anomalies


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    profil: ProfilEcarts,
) -> dict[str, Any]:
    """Construit un FeatureCollection des boites au rattachement fautif.

    `nombre_materiels` est reporte : il distingue une boite a deux materiels
    d'une boite a dix, que le seul code d'erreur confondrait.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": a["type_anomalie"],
                "fichier_source": FICHIER_JONCTION,
                "id_jonction": a["id_jonction"],
                "type_jonction": a["type_jonction"],
                "nombre_materiels": a["nombre_materiels"],
            },
            "geometry": a["geometrie"],
        }
        for a in anomalies
    ]
    return normaliser_geojson_ecarts({"type": "FeatureCollection", "features": features}, profil)


# ---------------------------------------------------------------------------
# Orchestration CLI
# ---------------------------------------------------------------------------


def executer_analyse(
    repertoire: str,
    types_retenus: frozenset[str],
    profil: ProfilEcarts,
    fichier_sortie: str,
    sortie: str | None = None,
    chemin_gml: Path | None = None,
) -> dict[str, Any]:
    """Execute la detection du rattachement au materiel et ecrit les ecarts.

    Le moteur releve les deux sens d'ecart ; le controle appelant ne retient que
    celui de son code. Sans GML, le controle se declare sans objet : la
    conversion ne conserve qu'un materiel par boite, aucun decompte n'y est
    possible.
    """
    repertoire_resolu = Path(repertoire).resolve()
    gml_resolu, motif = resoudre_chemin_gml(repertoire_resolu, chemin_gml)
    if gml_resolu is None:
        return rapport_sans_objet(
            f"{motif} : le décompte des matériels ne se lit que dans le GML",
            source=SOURCE_GML,
            nombre_boites_controlees=0,
        )

    racine = charger_racine(gml_resolu)
    boites = lire_boites(racine)
    anomalies = filtrer_par_type(detecter_anomalies(boites, compter_materiels_par_ouvrage(racine)), types_retenus)
    geojson_ecarts = construire_geojson_ecarts(anomalies, profil)

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else str(repertoire_resolu)
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, os.path.join(dossier_sortie, fichier_sortie))

    return {
        "succes": True,
        "source": SOURCE_GML,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_anomalies_par_type(anomalies),
        "nombre_boites_controlees": len(boites),
        "sortie": chemin_ecrit,
    }
