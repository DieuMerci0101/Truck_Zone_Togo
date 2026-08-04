import enum


class UserRole(str, enum.Enum):
    chauffeur = "chauffeur"
    proprietaire = "proprietaire"
    mecanicien = "mecanicien"
    admin = "admin"


class CategoriePermis(str, enum.Enum):
    C = "C"
    CE = "CE"
    D = "D"


class DisponibiliteChauffeur(str, enum.Enum):
    disponible = "disponible"
    en_mission = "en_mission"
    indisponible = "indisponible"


class TypeTransport(str, enum.Enum):
    marchandises = "marchandises"
    conteneurs = "conteneurs"
    vehicules_lourds = "vehicules_lourds"
    transport_personnes = "transport_personnes"
    produits_dangereux = "produits_dangereux"
    frigorifique = "frigorifique"
    autre = "autre"


class TypeActivite(str, enum.Enum):
    transport = "transport"
    logistique = "logistique"
    btp = "btp"
    agriculture = "agriculture"
    minier = "minier"
    autre = "autre"


class TypeCamion(str, enum.Enum):
    porteur = "porteur"
    semi_remorque = "semi_remorque"
    benne = "benne"
    citerne = "citerne"
    frigorifique = "frigorifique"
    bache = "bache"
    plateau = "plateau"
    benne_soulevable = "benne_soulevable"
    autre = "autre"


class EtatCamion(str, enum.Enum):
    bon_etat = "bon_etat"
    excellent = "excellent"
    bon = "bon"
    use = "use"
    en_reparation = "en_reparation"


class TypeContrat(str, enum.Enum):
    cdd = "CDD"
    cdi = "CDI"
    mission_ponctuelle = "Mission ponctuelle"


class StatutOffre(str, enum.Enum):
    active = "active"
    pourvue = "pourvue"
    expiree = "expirée"


class TypeDocument(str, enum.Enum):
    permis = "permis"
    cni = "cni"
    passeport = "passeport"
    certificat = "certificat"
    assurance = "assurance"
    casier = "casier"
    rccm = "rccm"
    patente = "patente"
    diplome = "diplome"
    photo_identite = "photo_identite"


class StatutDocument(str, enum.Enum):
    en_attente = "en_attente"
    valide = "valide"
    rejete = "rejete"


class TarificationMecanicien(str, enum.Enum):
    gratuit = "Gratuit"
    payant = "Payant"
    sur_devis = "Sur devis"


class DisponibiliteMecanicien(str, enum.Enum):
    disponible = "disponible"
    occupe = "occupe"
    indisponible = "indisponible"


class TypePanne(str, enum.Enum):
    mecanique = "Mécanique"
    pneumatique = "Pneumatique"
    electricite = "Électricité"
    carrosserie = "Carrosserie"
    autre = "Autre"


class Urgence(str, enum.Enum):
    faible = "Faible"
    moyenne = "Moyenne"
    haute = "Haute"
    critique = "Critique"


class StatutAssistance(str, enum.Enum):
    en_attente = "en_attente"
    pris_en_charge = "pris_en_charge"
    assignee = "assignee"
    en_cours = "en_cours"
    terminee = "terminee"


class TypeConversation(str, enum.Enum):
    directe = "directe"
    groupe = "groupe"


class TypeMessage(str, enum.Enum):
    texte = "texte"
    image = "image"
    fichier = "fichier"
    audio = "audio"


class TypeIncident(str, enum.Enum):
    accident = "Accident"
    panne = "Panne"
    embouteillage = "Emboutiillage"
    route_degradee = "Route dégradée"
    autre = "Autre"


class GraviteIncident(str, enum.Enum):
    faible = "Faible"
    moyenne = "Moyenne"
    grave = "Grave"
    mortel = "Mortel"


class StatutIncident(str, enum.Enum):
    declare = "declare"
    en_cours = "en_cours"
    traite = "traite"
    cloture = "cloture"


class TypeNotification(str, enum.Enum):
    message = "message"
    incident = "incident"
    assistance = "assistance"
    document = "document"
    systeme = "systeme"
    admin = "admin"
