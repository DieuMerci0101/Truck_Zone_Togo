import logging
import smtplib
import traceback
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import get_settings

logger = logging.getLogger(__name__)


def _send_email(to_email: str, subject: str, html_body: str, plain_body: str | None = None) -> bool:
    """
    Envoie un email via SMTP (STARTTLS port 587/25, ou SSL port 465).
    Retourne True en cas de succès, False sinon. Log détaillé en cas d'erreur.
    """
    settings = get_settings()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.email_from
    msg["To"] = to_email

    msg.attach(MIMEText(plain_body or html_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                server.ehlo()
                server.login(settings.smtp_user, settings.smtp_password)
                server.sendmail(settings.email_from, to_email, msg.as_string())
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(settings.smtp_user, settings.smtp_password)
                server.sendmail(settings.email_from, to_email, msg.as_string())
        logger.info("[EMAIL] Envoyé « %s » à %s", subject, to_email)
        return True
    except Exception as exc:
        logger.error(
            "[EMAIL] Échec de l'envoi « %s » à %s : %s\n%s",
            subject,
            to_email,
            exc,
            traceback.format_exc(),
        )
        return False


def send_otp_email(to_email: str, otp_code: str, user_name: str = "") -> bool:
    """
    Envoie un email avec un code OTP de réinitialisation de mot de passe.
    Retourne True si l'envoi a réussi, False sinon.
    """
    settings = get_settings()

    if not settings.smtp_user or not settings.smtp_password:
        logger.warning("[EMAIL] SMTP non configuré. Code OTP pour %s : %s", to_email, otp_code)
        return True

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

    Si vous n'avez pas demandé cette réinitialisation, ignorez cet email.
    """

    return _send_email(to_email, subject, html_body, plain_body)


def send_document_rejection_email(to_email: str, user_name: str, document_type: str, motif: str) -> bool:
    """
    Envoie un email à l'utilisateur pour l'informer du rejet de son document,
    avec le motif précis et les démarches de re-soumission.
    """
    settings = get_settings()

    if not settings.smtp_user or not settings.smtp_password:
        logger.warning("[EMAIL] SMTP non configuré. Pas d'email de rejet de document pour %s", to_email)
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

    if not settings.smtp_user or not settings.smtp_password:
        logger.warning("[EMAIL] SMTP non configuré. Pas d'email d'activation pour %s", to_email)
        return False
    subject = "Togo Truck Connect - Votre compte a été validé"
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
                <p class="greeting">Félicitations, votre compte Togo Truck Connect a été validé !</p>
                <p class="info">En tant que <strong>{role_label}</strong>, vous pouvez maintenant accéder à toutes les fonctionnalités de la plateforme.</p>
                <div class="badge">✓ Compte activé — Accès complet</div>
                <p class="info">Que pouvez-vous faire maintenant ?</p>
                <ol class="steps">
                    <li>Vous connecter à votre compte ;</li>
                    <li>Accéder à l'ensemble de votre tableau de bord ;</li>
                    <li>Déposer des offres, consulter les demandes et échanger avec la communauté.</li>
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
    Togo Truck Connect - Votre compte a été validé

    Félicitations, votre compte Togo Truck Connect a été validé !

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

    if not settings.smtp_user or not settings.smtp_password:
        logger.warning("[EMAIL] SMTP non configuré. Pas d'email de rejet de dossier pour %s", to_email)
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

    if not settings.smtp_user or not settings.smtp_password:
        logger.warning("[EMAIL] SMTP non configuré. Pas d'email de bienvenue pour %s", to_email)
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
