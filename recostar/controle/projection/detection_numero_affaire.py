"""
Moteur de detection des anomalies du numero de dossier d'une livraison.

Deux codes du verificateur y sont rendus, en cascade :

    le numero ne suit aucun des six modeles       -> E-0005
    il en suit un, mais sa reference DR est inconnue -> E-0006

Une cascade, et non deux constats independants
-----------------------------------------------
Un numero qui ne suit aucun modele n'a pas de reference a resoudre : le second
constat n'a alors rien a juger. Les deux regles sont donc **exclusives par
construction**, et dans cet ordre — c'est aussi celui des corrections : mettre le
numero au bon format, puis verifier a quelle DR il renvoie.

Trois des six modeles ne portent aucune reference
--------------------------------------------------
`type4` (identifiant RACING opaque), `type5` (numero interne) et `type6` (dossier
OSR) sont bien formes mais ne designent aucune direction regionale. Ils sont donc
conformes a E-0005 et **hors du perimetre d'E-0006** : il n'y a rien a resoudre,
et rendre une anomalie reviendrait a reprocher a un numero de ne pas porter ce
que son modele ne prevoit pas. Les modeles et leur champ de reference vivent dans
`fonctions_communes.numero_affaire`.

Ce sont exactement les numeros qu'`affaire_exclue_du_controle` ecarte deja des
controles d'emprise, pour la meme raison.

Une anomalie par livraison, sans geometrie
-------------------------------------------
Le defaut porte sur le **numero de dossier**, non sur un objet du reseau : aucune
entite ne le localise, et la feature d'ecart n'a donc pas de geometrie. C'est le
seul cas du projet, et il est assume — rattacher arbitrairement l'anomalie a une
entite du jeu designerait un innocent.

Referentiel : `projection/fichiers_dr/reference_dr.json`, celui-la meme que lisent
les controles d'emprise. Les cles y sont comparees en majuscules, comme le fait
deja `construire_index`.
"""

import os
from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.ecarts import filtrer_par_type
from recostar.controle.fonctions_communes.emprise_dr import CHEMIN_REFERENCE_DR, charger_references
from recostar.controle.fonctions_communes.geojson import (
    ProfilEcarts,
    compter_ecarts_par_type,
    ecrire_geojson_si_anomalies,
    normaliser_geojson_ecarts,
)
from recostar.controle.fonctions_communes.numero_affaire import (
    NOMS_MODELES,
    reconnaitre,
    references_connues,
)

# Types d'anomalie produits par le moteur, un par code rendu.
TYPE_MODELE_INCONNU: str = "numero_dossier_hors_modele"
TYPE_DR_INCONNUE: str = "numero_dossier_dr_inconnue"

# Identite de l'entite en anomalie : c'est le numero lui-meme, faute d'objet.
COUCHE_SOURCE: str = "_numero_affaire"


def detecter_anomalies(numero_affaire: str, references: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Releve l'anomalie du numero de dossier, s'il en porte une.

    Au plus une : les deux regles sont exclusives, et un numero conforme dont la
    DR est connue — ou dont le modele n'en porte pas — n'en produit aucune.
    """
    reconnu = reconnaitre(numero_affaire)
    if reconnu is None:
        return [
            {
                "type_anomalie": TYPE_MODELE_INCONNU,
                "numero_affaire": numero_affaire,
                "modele": None,
                "reference_dr": None,
                "message": (
                    f"Le numéro de dossier « {numero_affaire} » ne correspond à aucun "
                    f"des modèles attendus ({', '.join(NOMS_MODELES)})"
                ),
            }
        ]

    champ = reconnu.modele.champ_reference
    # Les trois modeles sans reference sont conformes des lors qu'ils suivent
    # leur forme : il n'y a aucune DR a resoudre.
    if champ is None or reconnu.reference is None:
        return []

    if reconnu.reference.upper() in references_connues(references, champ):
        return []
    return [
        {
            "type_anomalie": TYPE_DR_INCONNUE,
            "numero_affaire": numero_affaire,
            "modele": reconnu.modele.nom,
            "reference_dr": reconnu.reference,
            "message": (
                f"La référence « {reconnu.reference} » du numéro de dossier ne correspond "
                f"à aucun {champ} du référentiel des directions régionales"
            ),
        }
    ]


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    profil: ProfilEcarts,
) -> dict[str, Any]:
    """Construit un FeatureCollection de l'anomalie du numero de dossier.

    La feature n'a pas de geometrie : le defaut porte sur le numero, qu'aucune
    entite du jeu ne localise. Aucun crs n'est propage pour la meme raison.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": a["type_anomalie"],
                "fichier_source": COUCHE_SOURCE,
                "id_entite": a["numero_affaire"],
                "numero_affaire": a["numero_affaire"],
                "modele_reconnu": a["modele"],
                "reference_dr": a["reference_dr"],
                "message": a["message"],
            },
            "geometry": None,
        }
        for a in anomalies
    ]
    return normaliser_geojson_ecarts({"type": "FeatureCollection", "features": features}, profil)


def executer_analyse(
    repertoire: str,
    numero_affaire: str | None,
    types_retenus: frozenset[str],
    profil: ProfilEcarts,
    fichier_sortie: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute un controle du numero de dossier en mode CLI.

    Le repertoire n'est lu que pour situer la sortie : le controle ne juge que le
    numero d'affaire et le referentiel des directions regionales.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }
    if not numero_affaire:
        return {"succes": False, "erreur": "Parametre --numero_affaire requis"}

    references, erreur = charger_references(CHEMIN_REFERENCE_DR)
    if references is None or erreur is not None:
        return {"succes": False, "erreur": erreur}

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    # Le moteur releve les deux constats ; le controle appelant ne retient que
    # celui de son code.
    anomalies = filtrer_par_type(detecter_anomalies(numero_affaire, references), types_retenus)
    geojson_ecarts = construire_geojson_ecarts(anomalies, profil)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, os.path.join(dossier_sortie, fichier_sortie))

    reconnu = reconnaitre(numero_affaire)
    return {
        "succes": True,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_ecarts_par_type(geojson_ecarts),
        "numero_affaire": numero_affaire,
        "modele_reconnu": reconnu.modele.nom if reconnu is not None else None,
        "reference_dr": reconnu.reference if reconnu is not None else None,
        "nombre_references_dr": len(references),
        "sortie": chemin_ecrit,
    }
