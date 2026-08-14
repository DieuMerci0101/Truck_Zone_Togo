import asyncio
import logging
import re
import smtplib
import socket
import ssl
import traceback
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from app.config import get_settings

# Garantit que les logs d'envoi d'email sont visibles dans les logs Render
# (no-op si uvicorn a déjà configuré le root logger).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger(__name__)


class EmailSendError(Exception):
    """Échec RÉEL d'envoi SMTP (connexion, TLS, authentification, rejet serveur).
    Transporte le message d'erreur brut du serveur SMTP pour le diagnostic.
    """


def _resolve_from(settings) -> str:
    """Expéditeur réel de l'email : EMAIL_FROM explicite, sinon le compte SMTP
    authentifié (MAIL_USERNAME / SMTP_USER) — recommandé avec Gmail."""
    if settings.email_from and settings.email_from.strip():
        return settings.email_from.strip()
    if settings.smtp_user and settings.smtp_user.strip():
        return settings.smtp_user.strip()
    return "TogoTruckConnect <noreply@togotruckconnect.com>"


def _split_from(from_addr: str) -> tuple[str | None, str]:
    """Découpe « Nom <email@domaine> » en (nom, email). L'API Brevo attend un
    objet sender séparé (name + email), contrairement au SMTP."""
    m = re.match(r"^\s*(?:(.*?)\s*<([^>]+)>|([^<@\s]+@[^>\s]+))\s*$", from_addr)
    if m:
        if m.group(1) and m.group(2):
            return (m.group(1).strip() or None, m.group(2).strip())
        return (None, m.group(3).strip())
    return (None, from_addr.strip())


def _send_via_brevo_api(
    settings,
    to_email: str,
    subject: str,
    html_body: str,
    plain_body: str | None = None,
) -> bool:
    """
    Envoi via l'API HTTP Brevo (POST https://api.brevo.com/v3/smtp/email).
    Port 443 (HTTPS) : PAS bloqué par Render, contrairement aux ports SMTP
    25/465/587 sur les services gratuits (depuis le 26/09/2025).
    """
    name, from_email = _split_from(_resolve_from(settings))
    sender = {"email": from_email}
    if name:
        sender["name"] = name

    payload = {
        "sender": sender,
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_body,
        "textContent": plain_body or html_body,
    }
    headers = {
        "accept": "application/json",
        "api-key": settings.brevo_api_key,
        "content-type": "application/json",
    }

    logger.info("[EMAIL] Envoi via API Brevo de « %s » à %s", subject, to_email)
    try:
        resp = httpx.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers=headers,
            timeout=15,
        )
    except Exception as exc:
        logger.error(
            "[EMAIL] Échec réseau API Brevo « %s » à %s : %s\n%s",
            subject,
            to_email,
            exc,
            traceback.format_exc(),
        )
        raise EmailSendError(f"{type(exc).__name__}: {exc}") from exc

    if resp.status_code >= 400:
        logger.error(
            "[EMAIL] API Brevo refusée « %s » à %s : HTTP %s %s",
            subject,
            to_email,
            resp.status_code,
            resp.text[:300],
        )
        raise EmailSendError(
            f"Brevo API HTTP {resp.status_code}: {resp.text[:200]}"
        )

    logger.info("[EMAIL] Envoyé via API Brevo « %s » à %s", subject, to_email)
    return True


def _smtp_is_configured(settings) -> bool:
    return bool(
        settings.smtp_host
        and settings.smtp_port
        and settings.smtp_user
        and settings.smtp_password
    )


def _mail_is_configured(settings) -> bool:
    """Un canal d'envoi est-il disponible ? API Brevo (recommandé sur Render)
    OU SMTP. Les deux débloquent l'envoi réel."""
    return bool(settings.brevo_api_key) or _smtp_is_configured(settings)


def _smtp_connect(host: str, port: int, *, ssl_mode: bool = False) -> smtplib.SMTP:
    """
    Ouvre une connexion SMTP en FORÇANT IPv4.

    Gmail (smtp.gmail.com) renvoie des adresses IPv6 (AAAA) en plus des IPv4.
    Sur Render, l'instance n'a souvent PAS de route IPv6 sortante : la connexion
    échoue alors avec « [Errno 101] Network is unreachable » avant même le TLS.
    La résolution explicite `AF_INET` garantit une connexion IPv4 (port 587
    STARTTLS ou 465 SSL), sans changer la logique d'envoi.
    """
    timeout = 15
    try:
        addrinfo = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
    except socket.gaierror:
        # Repli : si aucune adresse IPv4 n'existe, laisser le système résoudre.
        addrinfo = socket.getaddrinfo(host, port, socket.SOCK_STREAM)
    _, _, _, _, sockaddr = addrinfo[0]

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(sockaddr)
    except Exception:
        sock.close()
        raise

    server = smtplib.SMTP()
    server.sock = sock
    server.host = host
    server._host = host  # Python 3.13 : `starttls()` lit `self._host` pour le SNI.
    server.timeout = timeout

    if ssl_mode:
        # Port 465 : TLS immédiat (SNI + vérification du certificat Gmail).
        context = ssl.create_default_context()
        server.sock = context.wrap_socket(sock, server_hostname=host)

    # Consomme le message de bienvenue (220) que `smtplib.SMTP(host, port)`
    # lit dans `connect()` : sinon la réponse à EHLO serait faussement lue
    # comme « 220 » et `starttls()` dirait STARTTLS non supporté.
    server.getreply()

    return server


async def email_task(func, *args, **kwargs) -> None:
    """
    Exécute un envoi SMTP bloquant dans un thread dédié (`asyncio.to_thread`),
    hors de l'event loop : un SMTP lent ou indisponible ne bloque plus la
    requête FastAPI. Journalise les erreurs sans jamais lever d'exception :
    l'échec d'un email ne doit pas faire échouer l'action métier (approbation,
    rejet, réinitialisation...).
    """
    try:
        ok = await asyncio.to_thread(func, *args, **kwargs)
        if not ok:
            logger.error("[EMAIL] L'envoi en arrière-plan a échoué (voir logs SMTP ci-dessus).")
    except Exception:
        logger.error("[EMAIL] Erreur inattendue lors de l'envoi en arrière-plan.", exc_info=True)


async def send_email_in_thread(func, *args, **kwargs) -> bool:
    """
    Exécute un envoi SMTP bloquant dans un thread dédié (hors de l'event loop)
    et RETOURNE le résultat réel de l'envoi (True/False) au lieu de le masquer.
    Le caller peut ainsi renvoyer une erreur HTTP 500 explicite en cas d'échec
    SMTP (fini les « faux positifs » : succès affiché alors qu'aucun email n'est parti).
    """
    return await asyncio.to_thread(func, *args, **kwargs)


def _send_email(to_email: str, subject: str, html_body: str, plain_body: str | None = None) -> bool:
    """
    Envoie un email.
    Si BREVO_API_KEY est défini → API HTTP Brevo (port 443, PAS bloqué par
    Render gratuit, contrairement au SMTP 25/465/587 depuis le 26/09/2025).
    Sinon → SMTP (STARTTLS port 587/25, ou SSL port 465).
    Retourne True en cas de succès, False sinon. Log détaillé en cas d'erreur.
    """
    settings = get_settings()
    from_addr = _resolve_from(settings)

    if settings.brevo_api_key:
        logger.info("[EMAIL] BREVO_API_KEY détecté — envoi via API HTTP Brevo.")
        _send_via_brevo_api(settings, to_email, subject, html_body, plain_body)
        return True

    if not _smtp_is_configured(settings):
        logger.error(
            "[EMAIL] SMTP non configuré — impossible d'envoyer « %s » à %s. "
            "Définir BREVO_API_KEY, ou SMTP_HOST / SMTP_PORT / SMTP_USER / "
            "SMTP_PASSWORD (ou MAIL_*) dans les variables d'environnement.",
            subject,
            to_email,
        )
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email

    msg.attach(MIMEText(plain_body or html_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        logger.info(
            "[EMAIL] Envoi de « %s » à %s via %s:%s",
            subject,
            to_email,
            settings.smtp_host,
            settings.smtp_port,
        )
        # Connexion forcée IPv4 (évite « [Errno 101] Network is unreachable »
        # quand Render ne route pas l'IPv6 renvoyée par Gmail).
        ssl_mode = settings.smtp_port == 465
        server = _smtp_connect(settings.smtp_host, settings.smtp_port, ssl_mode=ssl_mode)
        try:
            server.ehlo()
            if not ssl_mode:
                server.starttls()
                server.ehlo()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(from_addr, to_email, msg.as_string())
        finally:
            try:
                server.quit()
            except Exception:
                try:
                    server.close()
                except Exception:
                    pass
        logger.info("[EMAIL] Envoyé « %s » à %s", subject, to_email)
        return True
    except EmailSendError:
        raise
    except Exception as exc:
        logger.error(
            "[EMAIL] Échec de l'envoi « %s » à %s : %s\n%s",
            subject,
            to_email,
            exc,
            traceback.format_exc(),
        )
        # Propager l'erreur SMTP réelle : le caller décide de renvoyer un 500
        # explicite (fini les « faux positifs » : succès sans email parti).
        raise EmailSendError(f"{type(exc).__name__}: {exc}") from exc


def send_otp_email(to_email: str, otp_code: str, user_name: str = "") -> bool:
    """
    Envoie un email avec un code OTP de réinitialisation de mot de passe.
    Retourne True si l'envoi a réussi, False sinon.
    """
    settings = get_settings()

    if not _mail_is_configured(settings):
        logger.error(
            "[EMAIL] Aucun canal configuré — pas de code OTP envoyé à %s. "
            "Définir BREVO_API_KEY (recommandé) ou SMTP_HOST / SMTP_PORT / "
            "SMTP_USER / SMTP_PASSWORD.",
            to_email,
        )
        return False

    # URL publique du frontend (env `FRONTEND_URL`, défaut = production Vercel).
    verify_url = f"{settings.frontend_url.rstrip('/')}/verify-otp"

    subject = "Togo Truck Connect - Code de réinitialisation"

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #f4f7fa; margin: 0; padding: 20px; }}
            .container {{ max-width: 500px; margin: 0 auto; background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }}
            .header {{ background: linear-gradient(135deg, #1d4ed8, #1e3a8a); padding: 30px; text-align: center; }}
            .header h1 {{ color: white; margin: 0; font-size: 22px; }}
            .header p {{ color: rgba(255,255,255,0.8); margin: 8px 0 0; font-size: 14px; }}
            .body {{ padding: 30px; }}
            .greeting {{ font-size: 16px; color: #374151; margin-bottom: 20px; }}
            .otp-box {{ background: #f0f7ff; border: 2px dashed #3b82f6; border-radius: 12px; padding: 20px; text-align: center; margin: 20px 0; }}
            .otp-code {{ font-size: 32px; font-weight: bold; color: #1d4ed8; letter-spacing: 8px; }}
            .otp-label {{ font-size: 12px; color: #6b7280; margin-top: 8px; }}
            .btn {{ display:inline-block; background:#E59E00; color:#fff; text-decoration:none; padding:12px 28px; border-radius:8px; font-size:14px; font-weight:600; }}
            .info {{ font-size: 13px; color: #6b7280; line-height: 1.6; }}
            .footer {{ background: #f9fafb; padding: 20px; text-align: center; border-top: 1px solid #e5e7eb; }}
            .footer p {{ font-size: 11px; color: #9ca3af; margin: 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚛 Togo Truck Connect</h1>
                <p>Réinitialisation de mot de passe</p>
            </div>
            <div class="body">
                <p class="greeting">Bonjour{f' {user_name}' if user_name else ''},</p>
                <p class="info">Vous avez demandé la réinitialisation de votre mot de passe. Voici votre code de vérification :</p>
                <div class="otp-box">
                    <div class="otp-code">{otp_code}</div>
                    <div class="otp-label">Ce code expire dans 10 minutes</div>
                </div>
                <p style="text-align:center; margin: 24px 0;">
                    <a href="{verify_url}" class="btn">Saisir mon code</a>
                </p>
                <p class="info">Lien direct : <a href="{verify_url}" style="color:#b87e00;">{verify_url}</a></p>
                <p class="info">Si vous n'avez pas demandé cette réinitialisation, ignorez simplement cet email.</p>
            </div>
            <div class="footer">
                <p>© 2026 Togo Truck Connect - Plateforme du transport routier au Togo</p>
            </div>
        </div>
    </body>
    </html>
    """

    plain_body = f"""
    Togo Truck Connect - Code de réinitialisation

    Bonjour{f' {user_name}' if user_name else ''},

    Votre code de réinitialisation est : {otp_code}

    Ce code expire dans 10 minutes.

    Saisissez ce code sur la page : {verify_url}

    Si vous n'avez pas demandé cette réinitialisation, ignorez cet email.
    """

    return _send_email(to_email, subject, html_body, plain_body)


def send_document_rejection_email(to_email: str, user_name: str, document_type: str, motif: str) -> bool:
    """
    Envoie un email à l'utilisateur pour l'informer du rejet de son document,
    avec le motif précis et les démarches de re-soumission.
    """
    settings = get_settings()

    if not _mail_is_configured(settings):
        logger.warning("[EMAIL] Aucun canal configuré. Pas d'email de rejet de document pour %s", to_email)
        return False

    subject = "Togo Truck Connect - Motif de rejet de votre document"

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #f4f7fa; margin: 0; padding: 20px; }}
            .container {{ max-width: 500px; margin: 0 auto; background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }}
            .header {{ background: linear-gradient(135deg, #dc2626, #991b1b); padding: 30px; text-align: center; }}
            .header h1 {{ color: white; margin: 0; font-size: 22px; }}
            .body {{ padding: 30px; }}
            .greeting {{ font-size: 16px; color: #374151; margin-bottom: 16px; }}
            .info {{ font-size: 14px; color: #6b7280; line-height: 1.6; }}
            .motif-box {{ background: #fef2f2; border: 1px solid #fecaca; border-radius: 12px; padding: 16px; margin: 16px 0; }}
            .motif-box p {{ color: #dc2626; margin: 0; font-size: 14px; }}
            .steps {{ margin: 16px 0 0; padding-left: 18px; }}
            .steps li {{ font-size: 13px; color: #4b5563; line-height: 1.8; }}
            .footer {{ background: #f9fafb; padding: 20px; text-align: center; border-top: 1px solid #e5e7eb; }}
            .footer p {{ font-size: 11px; color: #9ca3af; margin: 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📄 Document rejeté</h1>
            </div>
            <div class="body">
                <p class="greeting">Bonjour {user_name},</p>
                <p class="info">Votre document « {document_type} » n'a pas été validé par l'administration.</p>
                <div class="motif-box">
                    <p><strong>Motif :</strong> {motif}</p>
                </div>
                <p class="info">Pour être vérifié, vous pouvez :</p>
                <ol class="steps">
                    <li>Vous connecter à votre compte sur Togo Truck Connect ;</li>
                    <li>Corriger le document concerné ;</li>
                    <li>Le re-soumettre depuis votre tableau de bord.</li>
                </ol>
            </div>
            <div class="footer">
                <p>© 2026 Togo Truck Connect - Plateforme du transport routier au Togo</p>
            </div>
        </div>
    </body>
    </html>
    """

    plain_body = f"""
    Togo Truck Connect - Motif de rejet de votre document

    Bonjour {user_name},

    Votre document « {document_type} » n'a pas été validé par l'administration.

    Motif : {motif}

    Pour être vérifié :
    1. Connectez-vous à votre compte sur Togo Truck Connect ;
    2. Corrigez le document concerné ;
    3. Re-soumettez-le depuis votre tableau de bord.
    """

    return _send_email(to_email, subject, html_body, plain_body)


def _role_label(role: str | None) -> str:
    return {
        "chauffeur": "chauffeur",
        "proprietaire": "propriétaire",
        "mecanicien": "mécanicien",
    }.get(role, "utilisateur")


def send_verification_approved_email(to_email: str, user_name: str, role: str | None = None) -> bool:
    """
    Envoie un email d'activation à l'utilisateur dès que l'administrateur
    valide son dossier de vérification (documents acceptés).
    """
    settings = get_settings()

    if not _mail_is_configured(settings):
        logger.warning("[EMAIL] Aucun canal configuré. Pas d'email d'activation pour %s", to_email)
        return False
    subject = "Togo Truck Connect - Votre compte a été validé"
    # URL publique du frontend (env `FRONTEND_URL`, défaut = production Vercel).
    login_url = f"{settings.frontend_url.rstrip('/')}/login"
    role_label = _role_label(role)

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #f4f7fa; margin: 0; padding: 20px; }}
            .container {{ max-width: 500px; margin: 0 auto; background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }}
            .header {{ background: linear-gradient(135deg, #E59E00, #b87e00); padding: 30px; text-align: center; }}
            .header h1 {{ color: white; margin: 0; font-size: 22px; }}
            .header p {{ color: rgba(255,255,255,0.9); margin: 8px 0 0; font-size: 14px; }}
            .body {{ padding: 30px; }}
            .greeting {{ font-size: 16px; color: #374151; margin-bottom: 16px; }}
            .info {{ font-size: 14px; color: #6b7280; line-height: 1.6; }}
            .badge {{ display: inline-block; background: #fef3c7; border: 1px solid #fcd34d; color: #92400e; border-radius: 999px; padding: 8px 18px; font-size: 13px; font-weight: 600; margin: 16px 0; }}
            .steps {{ margin: 16px 0 0; padding-left: 18px; }}
            .steps li {{ font-size: 13px; color: #4b5563; line-height: 1.8; }}
            .footer {{ background: #f9fafb; padding: 20px; text-align: center; border-top: 1px solid #e5e7eb; }}
            .footer p {{ font-size: 11px; color: #9ca3af; margin: 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚛 Togo Truck Connect</h1>
                <p>Votre compte a été validé</p>
            </div>
            <div class="body">
                <p class="greeting">Félicitations, votre compte Togo Truck Connect a été validé par l'administration !</p>
                <p class="info">Votre compte sur Togo Truck Connect a été validé par l'administration. Vous pouvez désormais vous connecter :</p>
                <p style="text-align:center; margin: 20px 0;">
                    <a href="{login_url}" style="display:inline-block; background:#E59E00; color:#fff; text-decoration:none; padding:12px 28px; border-radius:8px; font-size:14px; font-weight:600;">Se connecter</a>
                </p>
                <p class="info">En tant que <strong>{role_label}</strong>, vous pouvez maintenant accéder à toutes les fonctionnalités de la plateforme.</p>
                <div class="badge">✓ Compte activé — Accès complet</div>
                <p class="info">Que pouvez-vous faire maintenant ?</p>
                <ol class="steps">
                    <li>Vous connecter à votre compte ;</li>
                    <li>Accéder à l'ensemble de votre tableau de bord ;</li>
                    <li>Déposer des offres, consulter les demandes et échanger avec la communauté.</li>
                </ol>
                <p class="info">Lien direct : <a href="{login_url}" style="color:#b87e00;">{login_url}</a></p>
            </div>
            <div class="footer">
                <p>© 2026 Togo Truck Connect - Plateforme du transport routier au Togo</p>
            </div>
        </div>
    </body>
    </html>
    """

    plain_body = f"""
    Togo Truck Connect - Votre compte a été validé

    Votre compte sur Togo Truck Connect a été validé par l'administration.
    Vous pouvez désormais vous connecter : {login_url}

    En tant que {role_label}, vous pouvez maintenant accéder à toutes les fonctionnalités de la plateforme.

    Vous pouvez vous connecter et utiliser l'ensemble de votre tableau de bord.
    """

    return _send_email(to_email, subject, html_body, plain_body)


def send_verification_rejection_email(to_email: str, user_name: str, motif: str, role: str | None = None) -> bool:
    """
    Envoie un email à l'utilisateur pour l'informer du rejet de son dossier
    d'inscription, avec le rôle, le motif saisi par l'administrateur et les
    démarches de re-soumission.
    """
    settings = get_settings()

    if not _mail_is_configured(settings):
        logger.warning("[EMAIL] Aucun canal configuré. Pas d'email de rejet de dossier pour %s", to_email)
        return False

    subject = "Togo Truck Connect - Motif de rejet de votre dossier de vérification"
    role_label = _role_label(role)

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #f4f7fa; margin: 0; padding: 20px; }}
            .container {{ max-width: 500px; margin: 0 auto; background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }}
            .header {{ background: linear-gradient(135deg, #dc2626, #991b1b); padding: 30px; text-align: center; }}
            .header h1 {{ color: white; margin: 0; font-size: 22px; }}
            .header p {{ color: rgba(255,255,255,0.8); margin: 8px 0 0; font-size: 14px; }}
            .body {{ padding: 30px; }}
            .greeting {{ font-size: 16px; color: #374151; margin-bottom: 16px; }}
            .info {{ font-size: 14px; color: #6b7280; line-height: 1.6; }}
            .role-box {{ background: #f3f4f6; border-radius: 8px; padding: 10px 14px; margin: 16px 0; font-size: 13px; color: #374151; }}
            .motif-box {{ background: #fef2f2; border: 1px solid #fecaca; border-radius: 12px; padding: 16px; margin: 16px 0; }}
            .motif-box p {{ color: #dc2626; margin: 0; font-size: 14px; }}
            .steps {{ margin: 16px 0 0; padding-left: 18px; }}
            .steps li {{ font-size: 13px; color: #4b5563; line-height: 1.8; }}
            .footer {{ background: #f9fafb; padding: 20px; text-align: center; border-top: 1px solid #e5e7eb; }}
            .footer p {{ font-size: 11px; color: #9ca3af; margin: 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚛 Togo Truck Connect</h1>
                <p>Dossier de vérification rejeté</p>
            </div>
            <div class="body">
                <p class="greeting">Bonjour {user_name},</p>
                <p class="info">Votre dossier en tant que <strong>{role_label}</strong> nécessite une mise à jour.</p>
                <div class="motif-box">
                    <p><strong>Motif :</strong> {motif}</p>
                </div>
                <p class="info">Merci de vous connecter pour renvoyer le document conforme.</p>
                <p class="info">Détails supplémentaires :</p>
                <ol class="steps">
                    <li>Connectez-vous à votre compte ;</li>
                    <li>Corrigez les informations et documents demandés ;</li>
                    <li>Re-soumettez votre dossier depuis votre tableau de bord.</li>
                </ol>
                <p class="info">Vous recevrez également une notification dans votre espace avec ce même motif.</p>
            </div>
            <div class="footer">
                <p>© 2026 Togo Truck Connect - Plateforme du transport routier au Togo</p>
            </div>
        </div>
    </body>
    </html>
    """

    plain_body = f"""
    Togo Truck Connect - Motif de rejet de votre dossier de vérification

    Bonjour {user_name},

    Votre dossier en tant que {role_label} nécessite une mise à jour.

    Motif : {motif}

    Merci de vous connecter pour renvoyer le document conforme.

    Vous recevrez également une notification dans votre espace avec ce même motif.
    """

    return _send_email(to_email, subject, html_body, plain_body)


def send_welcome_email(to_email: str, user_name: str) -> bool:
    """
    Envoie un email de bienvenue après inscription.
    """
    settings = get_settings()

    if not _mail_is_configured(settings):
        logger.warning("[EMAIL] Aucun canal configuré. Pas d'email de bienvenue pour %s", to_email)
        return False

    subject = "Bienvenue sur Togo Truck Connect !"

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #f4f7fa; margin: 0; padding: 20px; }}
            .container {{ max-width: 500px; margin: 0 auto; background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }}
            .header {{ background: linear-gradient(135deg, #1d4ed8, #1e3a8a); padding: 30px; text-align: center; }}
            .header h1 {{ color: white; margin: 0; font-size: 22px; }}
            .body {{ padding: 30px; }}
            .greeting {{ font-size: 16px; color: #374151; margin-bottom: 16px; }}
            .info {{ font-size: 14px; color: #6b7280; line-height: 1.6; }}
            .footer {{ background: #f9fafb; padding: 20px; text-align: center; border-top: 1px solid #e5e7eb; }}
            .footer p {{ font-size: 11px; color: #9ca3af; margin: 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚛 Bienvenue {user_name} !</h1>
            </div>
            <div class="body">
                <p class="greeting">Votre compte a été créé avec succès !</p>
                <p class="info">Vous pouvez maintenant vous connecter et accéder à votre espace personnalisé.</p>
            </div>
            <div class="footer">
                <p>© 2026 Togo Truck Connect</p>
            </div>
        </div>
    </body>
    </html>
    """

    plain_body = f"""
    Bienvenue sur Togo Truck Connect !

    Bonjour {user_name},

    Votre compte a été créé avec succès !
    Vous pouvez maintenant vous connecter et accéder à votre espace personnalisé.
    """

    return _send_email(to_email, subject, html_body, plain_body)


def send_simple_notification_email(
    to_email: str, subject: str, body: str, lien: str | None = None
) -> bool:
    """
    Email court de notification (module 2 : notifications multi-canal).
    `body` = texte brut du message ; un lien optionnel est ajouté en pied.
    """
    settings = get_settings()

    if not _mail_is_configured(settings):
        logger.warning(
            "[EMAIL] Aucun canal configuré. Notification email ignorée pour %s", to_email
        )
        return False

    login_url = f"{settings.frontend_url.rstrip('/')}/login"
    action_url = lien or login_url

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #f4f7fa; margin: 0; padding: 20px; }}
            .container {{ max-width: 500px; margin: 0 auto; background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }}
            .header {{ background: linear-gradient(135deg, #1d4ed8, #1e3a8a); padding: 24px; text-align: center; }}
            .header h1 {{ color: white; margin: 0; font-size: 18px; }}
            .body {{ padding: 30px; }}
            .body p {{ font-size: 14px; color: #374151; line-height: 1.6; }}
            .btn {{ display:inline-block; background:#E59E00; color:#fff; text-decoration:none; padding:12px 28px; border-radius:8px; font-size:14px; font-weight:600; }}
            .footer {{ background: #f9fafb; padding: 20px; text-align: center; border-top: 1px solid #e5e7eb; }}
            .footer p {{ font-size: 11px; color: #9ca3af; margin: 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚛 Togo Truck Connect</h1>
            </div>
            <div class="body">
                <p>{subject}</p>
                <p>{body}</p>
                <p style="text-align:center; margin: 24px 0;">
                    <a href="{action_url}" class="btn">Ouvrir</a>
                </p>
            </div>
            <div class="footer">
                <p>© 2026 Togo Truck Connect - Plateforme du transport routier au Togo</p>
            </div>
        </div>
    </body>
    </html>
    """

    plain_body = f"{subject}\n\n{body}\n\n{action_url}"

    return _send_email(to_email, subject, html_body, plain_body)
