"""
Moteur de detection : rattachement des noeuds du reseau a un cable existant.

Verifie qu'un noeud du reseau en service declare, dans son champ cables_href,
une ou plusieurs references resolvant toutes une entite **cable** existante du
jeu de donnees.

Entites controlees :
    RPD_CoupeCircuitAFusibles_Reco        RPD_SupportModules_Reco
    RPD_ModuleRaccordement_Reco           RPD_Terre_Reco
    RPD_OuvrageCollectifBranchement_Reco  RPD_PosteElectrique_Reco
    RPD_PointDeComptage_Reco              RPD_JeuBarres_Reco
    RPD_Jonction_Reco

Aucune autre entite n'est controlee.

Perimetre : entites au Statut UnderCommissionning ou Functional. Un noeud d'un
autre statut n'est pas encore — ou n'est plus — en service : l'exigence de
rattachement ne lui est pas opposable. Meme parti qu'E-6108.

Regles de gestion (une anomalie par reference fautive) :
  - cables_href_absent           : le champ n'est pas renseigne ;
  - cables_href_absent_noeud_terre : idem sur un noeud de terre, ou le
                                   defaut n'a pas la meme portee (cf.
                                   codes_verificateur.DEROGATIONS_NIVEAU) ;
  - cables_href_vide             : le champ est renseigne mais ne porte aucune
                                   reference exploitable ;
  - reference_malformee          : la reference ne peut pas etre confrontee
                                   telle quelle a un identifiant ;
  - cable_introuvable            : la reference ne resout aucune entite du jeu ;
  - reference_hors_couche_cable  : la reference resout une entite existante,
                                   mais qui n'est pas un cable ;
  - cable_telecom_sur_noeud_electrique : la reference resout un cable de
                                   telecommunication, alors que le noeud n'est
                                   pas une jonction de telecommunication ;
  - cable_electrique_sur_noeud_telecom : la reference resout un cable
                                   electrique, alors que le noeud est une
                                   jonction de telecommunication ;
  - cable_terre_sur_noeud_telecom : la reference resout un cable de terre, alors
                                   que le noeud est une jonction de
                                   telecommunication.

Les deux premieres qualifient le noeud et sont exclusives : sans reference, il
n'y a rien a resoudre. Les suivantes qualifient une reference et cumulent,
conformement a la convention des controles de relation du projet (E-9500,
E-6103, E-9502, E-6108) : un noeud declarant deux references fautives porte deux
anomalies,
chacune etant a corriger pour elle-meme.

Separation electrique / telecommunication
-----------------------------------------
Un cable de telecommunication ne se raccorde qu'a une RPD_Jonction_Reco dont le
TypeJonction vaut Telecom. Tout autre noeud qui le declare dans son cables_href
melange les deux reseaux : c'est le code E-6113 du verificateur.

Reciproquement, une jonction de telecommunication n'admet **que** du cable de
telecommunication. Les deux autres couches y sont fautives, sous deux codes
distincts : le cable electrique en E-6115, le cable de terre en E-6213.

Les trois regles partagent un seul discriminant, la nature du noeud, resolue par
`est_noeud_telecom`, et sont exclusives sur une meme reference : chaque couche de
cable n'en declenche qu'une. `classifier_separation_reseaux` les porte ensemble.

**E-6213, rattachement derogatoire.** Le verificateur libelle ce code « Un cable
de telecommunication ne doit pas etre lie a un noeud de telecommunication », ce
qui contredit E-6116 — lequel exige precisement ce rattachement. Le libelle est
tenu pour errone, et le code reaffecte par arbitrage metier au cable de terre sur
une jonction de telecommunication, seul cas du bloc « separation » qui restait
sans code. Le niveau du code, `moyenne`, est conserve : la mise a la terre est
une infrastructure partagee, son rattachement fautif ne declasse pas la
livraison comme le font E-6113 et E-6115.

Les regles s'evaluent apres la resolution de la couche, non avant : elles ne
portent que sur une reference qui aboutit **et** designe bien un cable. Une
reference introuvable ou visant un coffret releve des regles precedentes, et la
signaler deux fois n'apprendrait rien de plus.

Toutes les references doivent etre valides
------------------------------------------
Le rattachement n'est pas repute correct des lors qu'une reference aboutit : la
regle porte sur chaque identifiant declare. Une reference sans realite designe
soit un cable supprime, soit une entite d'une autre nature ; dans les deux cas
la donnee affirme un lien qui n'existe pas, que d'autres references valides ne
reparent pas. Meme parti qu'E-9400 pour ses references orphelines.

Distinguer l'identifiant inexistant de l'entite qui n'est pas un cable
----------------------------------------------------------------------
Les deux cas appellent des corrections differentes — retablir une entite
disparue, ou corriger un lien qui vise la mauvaise entite — et l'index des
seules couches de cable ne permet pas de les separer : il rendrait « introuvable »
toute reference visant, par exemple, un coffret bien present.

L'index est donc construit sur **toutes** les couches du repertoire (les
fichiers d'ecarts en sont exclus par `lister_fichiers_geojson`), et associe a
chaque identifiant le nom de sa couche. Le nom du fichier fait foi pour le type
de l'entite — c'est la convention de nommage RecoStaR `RPD_<Type>_Reco`, et la
seule information de type disponible, les features ne portant pas leur classe.
Meme parti qu'E-6108 et E-6211. La couche resolue est reportee au fichier
d'ecarts,
afin que la nature reelle de l'entite visee soit lisible.

Couches de cable reconnues : RPD_CableElectrique_Reco, RPD_CableTerre_Reco et
RPD_CableTelecommunication_Reco — les trois memes que pour les relations de
cheminement et de jonction.

References mal formees
----------------------
Une reference est mal formee lorsqu'elle ne peut pas etre confrontee telle
quelle aux identifiants du jeu :

  - forme XLink non resolue : fragment « #idXXXX », URN ou URL absolue. Le GML
    source admet ces formes (cf. `geojson_to_recostar`, qui reecrit les
    « #id » lors du renommage des identifiants) et l'export GeoJSON restitue
    l'attribut brut : la forme se retrouve donc telle quelle dans cables_href ;
  - valeur non textuelle : un objet ou un booleen ne designe aucune entite.

Le controle ne valide pas la **forme interne** de l'identifiant : aucun motif
d'identifiant n'est normatif dans le projet, et rejeter un jeton sur ce critere
signalerait des references parfaitement resolubles. Un jeton bien forme mais
sans correspondance releve de `cable_introuvable`.

Le decoupage accepte la virgule et l'espace, comme
`utils_cable.extraire_ids_cables_href` : les identifiants RecoStaR ne
contiennent ni l'une ni l'autre, le decoupage est donc sans ambiguite.

Geometrie des ecarts : celle du noeud fautif, qui porte la reference et donc le
defaut. Les noeuds sans geometrie propre heritent de celle de leur conteneur des
l'export (cf. `detection_localisation_noeud`) : l'ecart reste localisable dans
QGIS sans repli
supplementaire.

Versions : les champs Statut et cables_href sont identiques en RecoStaR V1.0 et
V1.1 ; le controle est agnostique de version.

Priorite : bloquant. Un noeud qui ne resout aucun cable est detache de la
topologie du reseau ; le recolement ne peut pas etre exploite en l'etat
(cf. PRIORITES_DECLASSANTES dans synthese_controles). Meme priorite qu'E-7102,
qui porte sur une exigence de rattachement de meme nature.

"""

import os
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.chargement import charger_features, parcourir_couches
from recostar.controle.fonctions_communes.ecarts import filtrer_par_type
from recostar.controle.fonctions_communes.geojson import (
    ProfilEcarts,
    compter_anomalies_par_type,
    ecrire_geojson_si_anomalies,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_CABLES_HREF,
    CHAMP_STATUT,
    CHAMP_TYPE_JONCTION,
    COUCHE_CABLE_ELECTRIQUE,
    COUCHE_CABLE_TELECOM,
    COUCHE_CABLE_TERRE,
    COUCHE_COUPE_CIRCUIT,
    COUCHE_JEU_BARRES,
    COUCHE_JONCTION,
    COUCHE_MODULE_RACCORDEMENT,
    COUCHE_OUVRAGE_COLLECTIF,
    COUCHE_POINT_DE_COMPTAGE,
    COUCHE_POSTE,
    COUCHE_SUPPORT_MODULES,
    COUCHE_TERRE,
    STATUTS_EN_SERVICE,
)
from recostar.controle.fonctions_communes.separation_reseaux import est_noeud_telecom

# Couches controlees
COUCHES_CIBLES: tuple[str, ...] = (
    COUCHE_COUPE_CIRCUIT,
    COUCHE_MODULE_RACCORDEMENT,
    COUCHE_OUVRAGE_COLLECTIF,
    COUCHE_POINT_DE_COMPTAGE,
    COUCHE_SUPPORT_MODULES,
    COUCHE_TERRE,
    COUCHE_POSTE,
    COUCHE_JEU_BARRES,
    COUCHE_JONCTION,
)

# Couches dont une reference cables_href doit designer une entite
# (frozenset -> appartenance en O(1))
COUCHES_CABLE: frozenset[str] = frozenset(
    {
        COUCHE_CABLE_ELECTRIQUE,
        COUCHE_CABLE_TERRE,
        COUCHE_CABLE_TELECOM,
    }
)

# Extension ajoutee aux noms de couche pour obtenir leur fichier
EXTENSION: str = ".geojson"


# Types d'anomalie produits par ce controle
TYPE_HREF_ABSENT: str = "cables_href_absent"
TYPE_HREF_ABSENT_NOEUD_TERRE: str = "cables_href_absent_noeud_terre"
TYPE_HREF_VIDE: str = "cables_href_vide"
TYPE_REFERENCE_MALFORMEE: str = "reference_malformee"
TYPE_CABLE_INTROUVABLE: str = "cable_introuvable"
TYPE_HORS_COUCHE_CABLE: str = "reference_hors_couche_cable"
TYPE_TELECOM_SUR_NOEUD_ELECTRIQUE: str = "cable_telecom_sur_noeud_electrique"
TYPE_ELECTRIQUE_SUR_NOEUD_TELECOM: str = "cable_electrique_sur_noeud_telecom"
TYPE_TERRE_SUR_NOEUD_TELECOM: str = "cable_terre_sur_noeud_telecom"


# Statuts des noeuds a controler (frozenset -> appartenance en O(1))
STATUTS_CONTROLES: frozenset[str] = STATUTS_EN_SERVICE

# Formes XLink non resolues : la reference y designe une cible par un fragment,
# une URN ou une URL, et non par un identifiant confrontable tel quel.
PREFIXE_FRAGMENT: str = "#"
PREFIXE_URN: str = "urn:"
SEPARATEUR_URL: str = "://"

# Jeton substitue a une valeur non textuelle (objet, booleen), afin qu'elle soit
# signalee comme reference mal formee et reste lisible dans le fichier d'ecarts.
JETON_NON_TEXTUEL: str = "<valeur non textuelle>"


# ---------------------------------------------------------------------------
# Extraction des references
# ---------------------------------------------------------------------------


def _decouper(valeur: Any) -> list[str]:
    """Decoupe la valeur brute de cables_href en jetons, sans les qualifier.

    Gere les formes presentes dans les donnees RecoStaR : chaine unique, chaine
    multiple separee par des virgules ou des espaces, et liste. Les identifiants
    ne contenant ni virgule ni espace, le decoupage est sans ambiguite.

    Une valeur d'un autre type ne designe aucune entite : elle est reduite a un
    jeton marqueur, que `est_reference_malformee` signale ensuite. Le booleen
    est ecarte explicitement, `bool` etant un sous-type de `int`.

    L'absence de valeur ne produit aucun jeton : elle n'est pas une reference
    mal formee mais une absence de reference, qualifiee par
    `classifier_rattachement`.
    """
    if valeur is None:
        return []
    if isinstance(valeur, str):
        return valeur.replace(",", " ").split()
    if isinstance(valeur, list):
        return [jeton for element in valeur for jeton in _decouper(element)]
    if isinstance(valeur, int) and not isinstance(valeur, bool):
        return [str(valeur)]
    return [JETON_NON_TEXTUEL]


def est_reference_malformee(jeton: str) -> bool:
    """Indique si un jeton ne peut pas etre confronte tel quel a un identifiant.

    Sont mal formees les formes XLink non resolues — fragment « #idXXXX », URN,
    URL absolue — que le GML source admet et que l'export GeoJSON restitue
    brutes, ainsi que les valeurs non textuelles.

    La forme interne de l'identifiant n'est pas jugee : aucun motif n'est
    normatif dans le projet, et rejeter un jeton sur ce critere signalerait des
    references parfaitement resolubles.
    """
    if jeton == JETON_NON_TEXTUEL:
        return True
    return jeton.startswith(PREFIXE_FRAGMENT) or jeton.lower().startswith(PREFIXE_URN) or SEPARATEUR_URL in jeton


def extraire_references(valeur: Any) -> tuple[frozenset[str], frozenset[str]]:
    """Extrait les references de cables_href, separees selon leur exploitabilite.

    Retourne (exploitables, malformees). Les doublons sont replies : une meme
    reference declaree deux fois designe un seul rattachement, et produirait
    sinon deux anomalies identiques.
    """
    exploitables: set[str] = set()
    malformees: set[str] = set()
    est_malformee = est_reference_malformee  # alias local (boucle)
    for jeton in _decouper(valeur):
        if est_malformee(jeton):
            malformees.add(jeton)
        else:
            exploitables.add(jeton)
    return frozenset(exploitables), frozenset(malformees)


# ---------------------------------------------------------------------------
# Chargement de l'index des entites
# ---------------------------------------------------------------------------


def est_cable(couche: str) -> bool:
    """Indique si une couche porte des entites de type cable."""
    return couche in COUCHES_CABLE


def indexer_entites(repertoire: str) -> tuple[dict[str, str], int, list[str]]:
    """Indexe {identifiant: couche} pour toutes les entites du repertoire.

    Retourne (index, nombre_cables, couches_cable_absentes). L'index porte sur
    toutes les couches, et non sur les seules couches de cable : c'est ce qui
    permet de distinguer une reference sans correspondance d'une reference
    visant une entite d'une autre nature.

    Le generateur `parcourir_couches` ne detient qu'une couche a la fois : seuls
    les identifiants sont conserves, dont le volume est sans rapport avec celui
    des geometries.
    """
    index: dict[str, str] = {}
    nombre_cables = 0
    couches_cable_vues: set[str] = set()
    for couche, features in parcourir_couches(repertoire):
        # Increment hisse hors de la boucle des features : le test de couche est
        # invariant, le resoudre une fois par entite serait inutile.
        increment_cable = 1 if est_cable(couche) else 0
        if increment_cable:
            couches_cable_vues.add(couche)
        for feature in features:
            identifiant = obtenir_id_feature(feature)
            if identifiant is None:
                continue
            index[identifiant] = couche
            nombre_cables += increment_cable
    return index, nombre_cables, sorted(COUCHES_CABLE - couches_cable_vues)


def parcourir_noeuds(repertoire: str) -> Iterator[tuple[str, list[dict[str, Any]], dict[str, Any] | None, bool]]:
    """Parcourt les couches controlees, une seule chargee a la fois.

    Retourne (couche, features, crs, absente). Le crs est remonte avec la couche
    plutot que relu ensuite : les couches d'un meme jeu partagent leur systeme
    de coordonnees, le premier renseigne suffit a le propager au fichier
    d'ecarts.

    Les couches absentes du repertoire sont remontees pour le rapport, sans
    interrompre le controle : un jeu ne contient pas necessairement tous les
    types de noeuds.
    """
    for couche in COUCHES_CIBLES:
        features, crs, absente = charger_features(repertoire, f"{couche}{EXTENSION}")
        yield couche, features, crs, absente


# ---------------------------------------------------------------------------
# Regles metier (fonctions pures, testables sans I/O)
# ---------------------------------------------------------------------------


def est_a_controler(couche: str, proprietes: Mapping[str, Any]) -> bool:
    """Indique si une entite entre dans le perimetre du controle.

    Deux conditions cumulatives : appartenir a une couche cible et porter un
    Statut UnderCommissionning ou Functional.
    """
    return couche in COUCHES_CIBLES and proprietes.get(CHAMP_STATUT) in STATUTS_CONTROLES


def classifier_separation_reseaux(couche_cable: str, noeud_telecom: bool) -> str | None:
    """Retourne le type d'anomalie de separation des reseaux, ou None.

    Les trois regles sont mutuellement exclusives sur une meme reference, chaque
    couche de cable n'en declenchant qu'une :

      - cable de telecommunication hors d'un noeud de telecommunication (E-6113) ;
      - cable electrique sur un noeud de telecommunication (E-6115) ;
      - cable de terre sur un noeud de telecommunication (E-6213).

    La jonction de telecommunication n'admet donc qu'un cable de
    telecommunication : les deux dernieres regles couvrent, ensemble, toutes les
    autres couches de cable du modele.

    La couche attendue est celle d'une reference deja resolue en cable.
    """
    if couche_cable == COUCHE_CABLE_TELECOM and not noeud_telecom:
        return TYPE_TELECOM_SUR_NOEUD_ELECTRIQUE
    if not noeud_telecom:
        return None
    if couche_cable == COUCHE_CABLE_ELECTRIQUE:
        return TYPE_ELECTRIQUE_SUR_NOEUD_TELECOM
    if couche_cable == COUCHE_CABLE_TERRE:
        return TYPE_TERRE_SUR_NOEUD_TELECOM
    return None


def classifier_rattachement(
    valeur_href: Any,
    couche_par_id: Mapping[str, str],
    noeud_telecom: bool = False,
    noeud_terre: bool = False,
) -> list[tuple[str, str | None, str | None]]:
    """Retourne les anomalies de rattachement d'un noeud.

    Chaque anomalie est un triplet (type_anomalie, reference, couche_resolue) ;
    la reference et la couche sont nulles lorsque l'anomalie qualifie le noeud
    et non l'une de ses references.

    `noeud_telecom` dit si le noeud est une jonction de telecommunication, seule
    admise a porter un cable de telecommunication. Sa valeur par defaut est le
    cas general : huit des neuf couches controlees sont electriques.

    L'absence de reference interrompt le classement : sans reference, il n'y a
    rien a resoudre, et signaler en outre une reference introuvable produirait
    une anomalie redondante issue d'une meme cause. Meme parti que la chaine de
    localisation pour un
    conteneur absent.

    Les references sont ensuite classees une a une : la regle porte sur chaque
    identifiant declare, une reference valide ne reparant pas une reference
    fautive. Le tri rend l'ordre des anomalies deterministe.

    La separation electrique / telecommunication est evaluee en dernier, sur une
    reference qui aboutit et designe bien un cable : une reference introuvable ou
    visant autre chose releve des regles precedentes. Ses deux regles, E-6113 et
    E-6115, sont portees par `classifier_separation_reseaux`.
    """
    if valeur_href is None:
        # Le noeud de terre porte son propre type : l'absence de rattachement y
        # est signalee sans declasser la livraison, la mise a la terre etant une
        # infrastructure partagee dont le cablage se declare ailleurs.
        return [(TYPE_HREF_ABSENT_NOEUD_TERRE if noeud_terre else TYPE_HREF_ABSENT, None, None)]

    exploitables, malformees = extraire_references(valeur_href)
    if not exploitables and not malformees:
        return [(TYPE_HREF_VIDE, None, None)]

    anomalies: list[tuple[str, str | None, str | None]] = [
        (TYPE_REFERENCE_MALFORMEE, reference, None) for reference in sorted(malformees)
    ]
    for reference in sorted(exploitables):
        couche = couche_par_id.get(reference)
        if couche is None:
            anomalies.append((TYPE_CABLE_INTROUVABLE, reference, None))
        elif not est_cable(couche):
            anomalies.append((TYPE_HORS_COUCHE_CABLE, reference, couche))
        else:
            separation = classifier_separation_reseaux(couche, noeud_telecom)
            if separation is not None:
                anomalies.append((separation, reference, couche))
    return anomalies


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def detecter_anomalies_couche(
    couche: str,
    features: list[dict[str, Any]],
    couche_par_id: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Detecte les rattachements fautifs d'une couche donnee.

    Une couche hors perimetre ne peut produire aucune anomalie : elle est
    ecartee sans etre parcourue.
    """
    if couche not in COUCHES_CIBLES:
        return []
    anomalies: list[dict[str, Any]] = []
    classifier = classifier_rattachement  # alias local (boucle)
    est_telecom = est_noeud_telecom  # alias local (boucle)
    for feature in features:
        proprietes = feature.get("properties") or {}
        if proprietes.get(CHAMP_STATUT) not in STATUTS_CONTROLES:
            continue
        anomalies.extend(
            {
                "type_anomalie": type_anomalie,
                "couche_noeud": couche,
                "id_noeud": obtenir_id_feature(feature),
                "statut": proprietes.get(CHAMP_STATUT),
                "type_jonction": proprietes.get(CHAMP_TYPE_JONCTION),
                "cables_href": proprietes.get(CHAMP_CABLES_HREF),
                "reference": reference,
                "couche_reference": couche_reference,
                "geometrie": feature.get("geometry"),
            }
            for type_anomalie, reference, couche_reference in classifier(
                proprietes.get(CHAMP_CABLES_HREF),
                couche_par_id,
                est_telecom(couche, proprietes),
                couche == COUCHE_TERRE,
            )
        )
    return anomalies


def compter_noeuds_a_controler(couche: str, features: list[dict[str, Any]]) -> int:
    """Compte les entites d'une couche entrant dans le perimetre."""
    if couche not in COUCHES_CIBLES:
        return 0
    return sum(1 for feature in features if (feature.get("properties") or {}).get(CHAMP_STATUT) in STATUTS_CONTROLES)


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
    """Construit un FeatureCollection des noeuds au rattachement fautif.

    `couche_noeud` nomme le type du noeud : les neuf couches controlees
    partagent le meme fichier d'ecarts, l'information serait sinon perdue.
    `cables_href` conserve la valeur brute du champ, afin que la reference
    fautive reste lisible dans son contexte de declaration. `type_jonction` est
    le discriminant de la separation electrique / telecommunication : sans lui,
    une anomalie E-6113 ne dirait pas pourquoi le noeud n'etait pas admis.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": a["type_anomalie"],
                "fichier_source": f"{a['couche_noeud']}{EXTENSION}",
                "couche_noeud": a["couche_noeud"],
                "id_noeud": a["id_noeud"],
                "statut": a["statut"],
                "type_jonction": a["type_jonction"],
                "cables_href": a["cables_href"],
                "reference": a["reference"],
                "couche_reference": a["couche_reference"],
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


def executer_analyse(
    repertoire: str,
    types_retenus: frozenset[str],
    profil: ProfilEcarts,
    fichier_sortie: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle du rattachement des noeuds aux cables en mode CLI.

    Indexe une fois les entites de toutes les couches, parcourt les neuf couches
    controlees et ecrit le fichier d'ecarts GeoJSON. Les couches absentes sont
    remontees au rapport sans bloquer : un jeu ne contient pas necessairement
    tous les types de noeuds.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    couche_par_id, nombre_cables, couches_cable_absentes = indexer_entites(repertoire_resolu)

    anomalies: list[dict[str, Any]] = []
    noeuds_analyses = 0
    noeuds_controles = 0
    couches_absentes: list[str] = []
    crs_ecarts: dict[str, Any] | None = None
    for couche, features, crs, absente in parcourir_noeuds(repertoire_resolu):
        if absente:
            couches_absentes.append(couche)
            continue
        if crs_ecarts is None:
            crs_ecarts = crs
        noeuds_analyses += len(features)
        noeuds_controles += compter_noeuds_a_controler(couche, features)
        anomalies.extend(detecter_anomalies_couche(couche, features, couche_par_id))

    # Le moteur a releve toutes les anomalies ; le controle appelant ne
    # retient que celles de son code. Les compteurs qui suivent portent donc
    # sur son perimetre, non sur celui du moteur.
    anomalies = filtrer_par_type(anomalies, types_retenus)
    geojson_ecarts = construire_geojson_ecarts(anomalies, profil, crs_ecarts)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, fichier_sortie)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_anomalies_par_type(anomalies),
        "nombre_noeuds_analyses": noeuds_analyses,
        "nombre_noeuds_controles": noeuds_controles,
        "nombre_noeuds_non_conformes": compter_noeuds_non_conformes(anomalies),
        "nombre_entites_indexees": len(couche_par_id),
        "nombre_cables_indexes": nombre_cables,
        "couches_absentes": couches_absentes,
        "couches_cable_absentes": couches_cable_absentes,
        "sortie": chemin_ecrit,
    }
