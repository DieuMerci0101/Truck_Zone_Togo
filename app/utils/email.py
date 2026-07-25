import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import get_settings


def send_otp_email(to_email: str, otp_code: str, user_name: str = "") -> bool:
    """
    Envoie un email avec un code OTP de réinitialisation de mot de passe.
    Retourne True si l'envoi a réussi, False sinon.
    """
    settings = get_settings()

    if not settings.smtp_user or not settings.smtp_password:
        print(f"[EMAIL] SMTP non configuré. Code OTP pour {to_email}: {otp_code}")
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

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.email_from
    msg["To"] = to_email

    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.email_from, to_email, msg.as_string())
        print(f"[EMAIL] OTP envoyé à {to_email}")
        return True
    except Exception as e:
        print(f"[EMAIL] Erreur envoi à {to_email}: {e}")
        print(f"[EMAIL] Code OTP pour {to_email}: {otp_code}")
        return False


def send_welcome_email(to_email: str, user_name: str) -> bool:
    """
    Envoie un email de bienvenue après inscription.
    """
    settings = get_settings()

    if not settings.smtp_user or not settings.smtp_password:
        print(f"[EMAIL] SMTP non configuré. Pas d'email de bienvenue pour {to_email}")
        return True

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

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.email_from
    msg["To"] = to_email

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.email_from, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[EMAIL] Erreur envoi bienvenue à {to_email}: {e}")
        return False
