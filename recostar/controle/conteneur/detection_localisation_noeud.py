"""
Moteur de detection : chaine de localisation des noeuds sans geometrie propre.

Certains noeuds du reseau ne portent pas de geometrie : leur position est celle
du conteneur qui les heberge, et l'emprise de ce conteneur est decrite par une
geometrie supplementaire. Le controle verifie que cette chaine est complete et
resolue de bout en bout :

    noeud (sans geometrie propre)
      -> conteneur_href                -> conteneur
      -> geometriesupplementaire_href  -> RPD_GeometrieSupplementaire_Reco
      -> geometrie valide

Deux perimetres, et non un seul
-------------------------------
Les regles de chaine ne valent que pour les noeuds qui n'ont pas le droit de
porter une geometrie : leur position ne peut venir que du conteneur.

    RPD_CoupeCircuitAFusibles_Reco   RPD_SupportModules_Reco
    RPD_JeuBarres_Reco               RPD_Terre_Reco
    RPD_ModuleRaccordement_Reco      RPD_PosteElectrique_Reco

La regle de geometrie directe s'etend a deux ouvrages de plus :

    RPD_PointDeComptage_Reco         RPD_OuvrageCollectifBranchement_Reco

Ces deux-la ont le droit de porter une geometrie propre — c'est meme la premiere
voie de localisation admise par E-6109 — mais pas en meme temps qu'un
rattachement a un conteneur : leur position serait alors decrite deux fois, par
deux sources libres de diverger. Leur chaine de conteneur, elle, reste du
ressort d'E-6109, qui la parcourt avec ses propres conteneurs autorises ; la
reevaluer ici produirait deux fois la meme anomalie sous deux codes.

Aucune autre entite n'est controlee.

Detection de la geometrie directe (indispensable)
-------------------------------------------------
Le champ `geometry` du GeoJSON ne peut pas etre teste tel quel. Les sept
extracteurs de `recostar_to_geojson` appliquent la meme regle — « heriter de la
geometrie du conteneur si pas de geometrie propre » — et renseignent donc
`geometry` meme lorsque le GML n'en porte aucune. Tester la simple presence
d'une geometrie signalerait la totalite des entites et mesurerait le
convertisseur, non la donnee.

Le discriminant est l'**egalite avec la geometrie du conteneur** : une geometrie
identique a celle du conteneur est heritee, donc absente a la source ; une
geometrie differente est propre a l'entite, donc directe. Verifie sur les jeux
de reference : 114 des 115 entites portent une geometrie strictement identique a
celle de leur conteneur.

Conteneurs reconnus : RPD_Coffret_Reco, RPD_Support_Reco,
RPD_BatimentTechnique_Reco et RPD_EnceinteCloturee_Reco — les quatre couches qui
alimentent le cache de geometries du convertisseur, donc les seules dont un
noeud puisse heriter sa position.

Regles de gestion, evaluees en cascade :
  - conteneur_absent                       : conteneur_href n'est pas renseigne ;
  - conteneur_introuvable                  : il ne resout aucun conteneur connu ;
  - geometrie_directe_presente             : le noeud porte une geometrie propre
                                             alors qu'il est rattache a un
                                             conteneur ;
  - geometrie_supplementaire_absente       : le conteneur ne porte pas de
                                             geometriesupplementaire_href ;
  - geometrie_supplementaire_introuvable   : cette reference ne resout aucune
                                             RPD_GeometrieSupplementaire_Reco ;
  - geometrie_supplementaire_invalide      : l'entite existe mais sa geometrie
                                             est absente ou vide.

L'absence de conteneur interrompt la cascade : sans conteneur, ni la comparaison
de geometrie ni la suite de la chaine ne sont evaluables, et les signaler
produirait des anomalies redondantes issues d'une meme cause. Meme parti que le
catalogue de materiel
pour un domaine de tension inconnu. La geometrie directe, elle, est un defaut
propre au noeud : elle n'interrompt pas la verification de la chaine du
conteneur, les deux pouvant coexister.

Une reference morte interrompt la chaine de la meme facon. Hors perimetre de
chaine, elle laisse en revanche la geometrie directe evaluable : le rattachement
existe bel et bien dans les attributs, et une geometrie portee sans conteneur
resolu ne peut venir que de l'entite elle-meme.

Un conteneur fautif rend non conformes **tous** les noeuds qu'il heberge : la
regle qualifie l'entite, pas le conteneur, et chaque noeud est effectivement
privee de localisation.

Versions : les champs de relation sont identiques en RecoStaR V1.0 et V1.1 ; le
controle est agnostique de version.

Priorite : bloquant.

"""

import os
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.chargement import charger_features
from recostar.controle.fonctions_communes.ecarts import filtrer_par_type
from recostar.controle.fonctions_communes.geojson import (
    PRIORITE_FORTE,
    ProfilEcarts,
    compter_anomalies_par_type,
    ecrire_geojson_si_anomalies,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)
from recostar.controle.fonctions_communes.localisation_conteneur import (
    TYPE_CONTENEUR_ABSENT,
    TYPE_CONTENEUR_INTROUVABLE,
    TYPE_GEOMSUPP_ABSENTE,
    TYPE_GEOMSUPP_INTROUVABLE,
    TYPE_GEOMSUPP_INVALIDE,
    Conteneur,
    classifier_chaine_conteneur,
    geometrie_ecart,
    geometrie_valide,
    indexer_conteneurs,
    indexer_geometries_supplementaires,
    possede_geometrie_propre,
)
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_CONTENEUR_HREF,
    COUCHE_COUPE_CIRCUIT,
    COUCHE_JEU_BARRES,
    COUCHE_MODULE_RACCORDEMENT,
    COUCHE_OUVRAGE_COLLECTIF,
    COUCHE_POINT_DE_COMPTAGE,
    COUCHE_POSTE,
    COUCHE_SUPPORT_MODULES,
    COUCHE_TERRE,
    EXTENSION_COUCHE,
)
from recostar.controle.fonctions_communes.proprietes import reference_href

# Couches dont la chaine de localisation est controlee de bout en bout : elles
# n'ont pas le droit de porter une geometrie, leur position vient du conteneur.
COUCHES_CIBLES: tuple[str, ...] = (
    COUCHE_COUPE_CIRCUIT,
    COUCHE_JEU_BARRES,
    COUCHE_MODULE_RACCORDEMENT,
    COUCHE_SUPPORT_MODULES,
    COUCHE_TERRE,
    COUCHE_POSTE,
)

# Ouvrages soumis a la seule regle de geometrie directe : ils peuvent se
# localiser par eux-memes, leur chaine de conteneur relevant d'E-6109.
COUCHES_OUVRAGES_LOCALISABLES: tuple[str, ...] = (
    COUCHE_POINT_DE_COMPTAGE,
    COUCHE_OUVRAGE_COLLECTIF,
)

# Couches parcourues par le moteur : l'union des deux perimetres. Tuple, car
# l'ordre fixe le parcours des fichiers et la resolution du crs.
COUCHES_PARCOURUES: tuple[str, ...] = COUCHES_CIBLES + COUCHES_OUVRAGES_LOCALISABLES

# Memes perimetres en frozenset : l'appartenance est testee par entite, elle
# doit etre en O(1).
COUCHES_CHAINE_CONTROLEE: frozenset[str] = frozenset(COUCHES_CIBLES)
COUCHES_CONTROLEES: frozenset[str] = frozenset(COUCHES_PARCOURUES)


# Types d'anomalie produits par ce controle
TYPE_GEOMETRIE_DIRECTE: str = "geometrie_directe_presente"

# Perimetre propre a chaque type d'anomalie. Le moteur sert trois controles et
# parcourt l'union des couches ; le denominateur du rapport, lui, doit suivre le
# controle appelant, sans quoi E-6105 et E-6106 annonceraient des entites qu'ils
# ne controlent pas.
COUCHES_PAR_TYPE: dict[str, frozenset[str]] = {
    TYPE_CONTENEUR_ABSENT: COUCHES_CHAINE_CONTROLEE,
    TYPE_CONTENEUR_INTROUVABLE: COUCHES_CHAINE_CONTROLEE,
    TYPE_GEOMETRIE_DIRECTE: COUCHES_CONTROLEES,
    TYPE_GEOMSUPP_ABSENTE: COUCHES_CHAINE_CONTROLEE,
    TYPE_GEOMSUPP_INTROUVABLE: COUCHES_CHAINE_CONTROLEE,
    TYPE_GEOMSUPP_INVALIDE: COUCHES_CHAINE_CONTROLEE,
}

# Priorite de repli des types d'anomalie dont le code d'erreur du verificateur
# n'est pas encore fixe (cf. COUPLES_A_QUALIFIER). Les types deja rattaches a un
# code tiennent leur priorite de son niveau, resolu une seule fois dans
# utils_geojson_commun ; cette constante ne les concerne plus.
PRIORITE_ANOMALIE: str = PRIORITE_FORTE


# Cles de la geometrie GeoJSON


# ---------------------------------------------------------------------------
# Chargement des index
# ---------------------------------------------------------------------------


def est_a_controler(couche: str) -> bool:
    """Indique si une couche entre dans le perimetre du moteur.

    Le perimetre est l'union des deux : les six couches sans geometrie propre,
    plus les deux ouvrages soumis a la seule regle de geometrie directe.
    """
    return couche in COUCHES_CONTROLEES


def chaine_conteneur_a_controler(couche: str) -> bool:
    """Indique si la chaine de localisation d'une couche est controlee ici.

    Le point de comptage et l'ouvrage collectif en sont exclus : E-6109 parcourt
    deja leur chaine, avec ses propres conteneurs autorises. La reevaluer ici
    produirait deux fois la meme anomalie sous deux codes differents.
    """
    return couche in COUCHES_CHAINE_CONTROLEE


def couches_du_controle(types_retenus: frozenset[str]) -> frozenset[str]:
    """Perimetre d'un controle, deduit des types d'anomalie qu'il retient.

    Le moteur parcourt l'union des perimetres ; chaque controle n'en couvre que
    la part de ses propres regles. Un type inconnu est ignore plutot que de
    lever : le moteur ne doit pas echouer sur un type que lui passe un appelant.
    """
    perimetres = [
        COUCHES_PAR_TYPE[type_anomalie] for type_anomalie in types_retenus if type_anomalie in COUCHES_PAR_TYPE
    ]
    if not perimetres:
        return frozenset()
    return frozenset().union(*perimetres)


def parcourir_noeuds(repertoire: str) -> Iterator[tuple[str, list[dict[str, Any]], bool]]:
    """Parcourt les couches controlees, une seule chargee a la fois.

    Retourne (couche, features, absente). Les couches absentes du repertoire
    sont remontees pour le rapport, sans interrompre le controle : un jeu ne
    contient pas necessairement tous les types de noeuds.
    """
    for couche in COUCHES_PARCOURUES:
        features, _, absente = charger_features(repertoire, f"{couche}{EXTENSION_COUCHE}")
        yield couche, features, absente


# ---------------------------------------------------------------------------
# Regle metier (fonction pure, testable sans I/O)
# ---------------------------------------------------------------------------


def classifier_noeud(
    geometrie: Any,
    reference_conteneur: str | None,
    conteneurs: Mapping[str, Conteneur],
    geometries_supplementaires: Mapping[str, dict[str, Any] | None],
    chaine_controlee: bool = True,
) -> list[str]:
    """Retourne les codes d'anomalie d'un noeud au regard de sa chaine.

    `chaine_controlee` distingue les deux perimetres : a False, seule la regle
    de geometrie directe est evaluee, la chaine du conteneur relevant d'E-6109.

    L'absence de conteneur interrompt la cascade : sans conteneur, ni la
    comparaison de geometrie ni la suite de la chaine ne sont evaluables. Elle
    ne dit rien non plus d'une geometrie directe : sans rattachement, une
    geometrie propre est la voie de localisation normale de ces ouvrages.

    Une reference morte interrompt la chaine de la meme facon. Hors perimetre de
    chaine, elle laisse la geometrie directe evaluable : le rattachement existe
    dans les attributs, et une geometrie portee sans conteneur resolu ne peut
    venir que de l'entite elle-meme.

    La geometrie directe n'interrompt pas la verification : c'est un defaut
    propre au noeud, qui peut coexister avec une chaine de conteneur rompue.
    Une geometrie egale a celle du conteneur est heritee, donc absente a la
    source — c'est le seul moyen de distinguer les deux depuis le GeoJSON.
    """
    if reference_conteneur is None:
        return [TYPE_CONTENEUR_ABSENT] if chaine_controlee else []

    conteneur = conteneurs.get(reference_conteneur)
    if conteneur is None:
        if chaine_controlee:
            return [TYPE_CONTENEUR_INTROUVABLE]
        return [TYPE_GEOMETRIE_DIRECTE] if geometrie_valide(geometrie) else []

    anomalies: list[str] = []
    # Discriminant partage avec E-6204 et E-6109 : une geometrie valide et
    # differente de celle du conteneur est propre a l'entite.
    if possede_geometrie_propre(geometrie, reference_conteneur, conteneurs):
        anomalies.append(TYPE_GEOMETRIE_DIRECTE)
    if chaine_controlee:
        rupture = classifier_chaine_conteneur(conteneur, geometries_supplementaires)
        if rupture is not None:
            anomalies.append(rupture)
    return anomalies


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def detecter_anomalies_couche(
    couche: str,
    features: list[dict[str, Any]],
    conteneurs: Mapping[str, Conteneur],
    geometries_supplementaires: Mapping[str, dict[str, Any] | None],
) -> list[dict[str, Any]]:
    """Detecte les chaines de localisation rompues d'une couche donnee.

    Une couche hors perimetre ne peut produire aucune anomalie : elle est ecartee
    sans etre parcourue.

    La geometrie de l'ecart est celle du noeud si elle existe, a defaut celle de
    son conteneur : un noeud sans position ne serait sinon pas localisable.
    """
    if not est_a_controler(couche):
        return []
    anomalies: list[dict[str, Any]] = []
    classifier = classifier_noeud  # alias local
    # Le perimetre de chaine ne depend que de la couche : resolu une seule fois,
    # hors de la boucle des entites.
    chaine_controlee = chaine_conteneur_a_controler(couche)
    for feature in features:
        proprietes = feature.get("properties") or {}
        reference = reference_href(proprietes, CHAMP_CONTENEUR_HREF)
        geometrie = feature.get("geometry")
        conteneur = conteneurs.get(reference) if reference is not None else None
        anomalies.extend(
            {
                "type_anomalie": type_anomalie,
                "couche_noeud": couche,
                "id_noeud": obtenir_id_feature(feature),
                "id_conteneur": reference,
                "id_geometrie_supplementaire": conteneur.href_geomsupp if conteneur is not None else None,
                "geometrie": geometrie_ecart(geometrie, conteneur),
            }
            for type_anomalie in classifier(
                geometrie, reference, conteneurs, geometries_supplementaires, chaine_controlee
            )
        )
    return anomalies


def compter_noeuds_a_controler(
    couche: str,
    features: list[dict[str, Any]],
    couches_controle: frozenset[str] = COUCHES_CONTROLEES,
) -> int:
    """Compte les entites d'une couche entrant dans le perimetre d'un controle.

    `couches_controle` vaut par defaut le perimetre du moteur ; chaque controle
    appelant passe le sien, plus etroit pour E-6105 et E-6106.
    """
    return len(features) if couche in couches_controle else 0


def compter_noeuds_non_conformes(anomalies: list[dict[str, Any]]) -> int:
    """Compte les noeuds distincts portant au moins une anomalie."""
    return len({(anomalie["couche_noeud"], anomalie["id_noeud"]) for anomalie in anomalies})


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    profil: ProfilEcarts,
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des chaines de localisation rompues.

    `couche_noeud` nomme le type du noeud : les six couches controlees partagent
    le meme fichier d'ecarts, l'information serait sinon perdue.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": a["type_anomalie"],
                "fichier_source": f"{a['couche_noeud']}{EXTENSION_COUCHE}",
                "couche_noeud": a["couche_noeud"],
                "id_noeud": a["id_noeud"],
                "id_conteneur": a["id_conteneur"],
                "id_geometrie_supplementaire": a["id_geometrie_supplementaire"],
                "priorite": PRIORITE_ANOMALIE,
            },
            "geometry": a["geometrie"],
        }
        for a in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return normaliser_geojson_ecarts(resultat, profil)


# ---------------------------------------------------------------------------
# Orchestration CLI
# ---------------------------------------------------------------------------


def _resoudre_crs(repertoire: str) -> dict[str, Any] | None:
    """Retourne le crs de la premiere couche cible presente.

    Les couches d'un meme jeu partagent leur systeme de coordonnees ; la
    premiere renseignee suffit a le propager au fichier d'ecarts.
    """
    for couche in COUCHES_PARCOURUES:
        _, crs, absente = charger_features(repertoire, f"{couche}{EXTENSION_COUCHE}")
        if not absente and crs is not None:
            return crs
    return None


def executer_analyse(
    repertoire: str,
    types_retenus: frozenset[str],
    profil: ProfilEcarts,
    fichier_sortie: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle de la chaine de localisation des noeuds en mode CLI.

    Indexe les conteneurs et les geometries supplementaires, parcourt les six
    couches controlees et ecrit le fichier d'ecarts GeoJSON. Les couches
    absentes sont remontees au rapport sans bloquer : un jeu ne contient pas
    necessairement tous les types de noeuds.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    conteneurs, conteneurs_absents = indexer_conteneurs(repertoire_resolu)
    geometries_supplementaires = indexer_geometries_supplementaires(repertoire_resolu)

    # Perimetre du controle appelant, resolu une fois : le moteur parcourt
    # l'union des couches, le denominateur du rapport ne compte que les siennes.
    couches_controle = couches_du_controle(types_retenus)

    anomalies: list[dict[str, Any]] = []
    noeuds_controles = 0
    couches_absentes: list[str] = []
    for couche, features, absente in parcourir_noeuds(repertoire_resolu):
        if absente:
            couches_absentes.append(couche)
            continue
        noeuds_controles += compter_noeuds_a_controler(couche, features, couches_controle)
        anomalies.extend(detecter_anomalies_couche(couche, features, conteneurs, geometries_supplementaires))

    # Le moteur a releve toutes les anomalies ; le controle appelant ne
    # retient que celles de son code. Les compteurs qui suivent portent donc
    # sur son perimetre, non sur celui du moteur.
    anomalies = filtrer_par_type(anomalies, types_retenus)
    geojson_ecarts = construire_geojson_ecarts(anomalies, profil, _resoudre_crs(repertoire_resolu))

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, fichier_sortie)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_anomalies_par_type(anomalies),
        "nombre_noeuds_controles": noeuds_controles,
        "nombre_noeuds_non_conformes": compter_noeuds_non_conformes(anomalies),
        "nombre_conteneurs": len(conteneurs),
        "nombre_geometries_supplementaires": len(geometries_supplementaires),
        "couches_absentes": couches_absentes,
        "couches_conteneur_absentes": conteneurs_absents,
        "sortie": chemin_ecrit,
    }
