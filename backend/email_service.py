"""
Email service using Brevo (formerly Sendinblue)
300 free emails per day!
"""

import os
import secrets
import re
from datetime import datetime, timedelta, timezone
from firebase_admin import firestore
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Try to import Brevo
try:
    import sib_api_v3_sdk
    from sib_api_v3_sdk.rest import ApiException
    BREVO_AVAILABLE = True
except ImportError:
    BREVO_AVAILABLE = False
    print("⚠️ Brevo email service not available. Install with: pip install sib-api-v3-sdk")

db = firestore.client()

# Brevo configuration
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "").strip()
SENDER_EMAIL = "neurosight.fyp@gmail.com"
SENDER_NAME = "NeuroSight"
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

# Validate API key format (only if package is available)
if BREVO_AVAILABLE:
    if not BREVO_API_KEY:
        print("ℹ🏆 Brevo API key not configured - email features will use fallback mode")
    elif not BREVO_API_KEY.startswith("xkeysib-"):
        print("⚠️ Invalid Brevo API key format (should start with 'xkeysib-')")
        BREVO_API_KEY = ""  # Disable to use fallback
else:
    if BREVO_API_KEY:
        print("⚠️ Brevo API key found but package not installed. Run: pip install sib-api-v3-sdk")

def generate_verification_code():
    """Generate 6-digit code"""
    code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
    print(f"[INFO] Generated verification code: {code}")
    return code

def send_verification_email(email: str, name: str, code: str):
    """Send verification email using Brevo"""
    
    print(f"[INFO] Sending email with code: {code} to {email}")
    
    # Fallback if Brevo not configured
    if not BREVO_AVAILABLE or not BREVO_API_KEY:
        print(f"[INFO] Verification code for {email}: {code}")
        return True
    
    try:
        # Configure Brevo API
        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key['api-key'] = BREVO_API_KEY
        
        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))
        
        # Email HTML
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background: #f5f8fa; }}
                .container {{ max-width: 600px; margin: 40px auto; background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 24px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #1da1f2 0%, #0d8bd9 100%); padding: 40px; text-align: center; }}
                .header h1 {{ color: white; margin: 0; font-size: 32px; }}
                .header p {{ color: rgba(255,255,255,0.9); margin: 10px 0 0 0; }}
                .content {{ padding: 40px; }}
                .welcome {{ font-size: 18px; color: #14171a; margin-bottom: 20px; }}
                .code-box {{ background: #f7f9fa; border: 2px dashed #1da1f2; border-radius: 12px; padding: 24px; text-align: center; margin: 30px 0; }}
                .code {{ font-size: 48px; font-weight: 700; letter-spacing: 8px; color: #1da1f2; font-family: 'Courier New', monospace; }}
                .validity {{ color: #657786; font-size: 13px; margin-top: 10px; }}
                .info {{ background: #fff4e6; border-left: 4px solid #ffad1f; padding: 16px; border-radius: 8px; color: #14171a; font-size: 14px; margin: 20px 0; }}
                .features {{ background: #f7f9fa; border-radius: 12px; padding: 20px; margin: 30px 0; }}
                .features h3 {{ color: #14171a; font-size: 18px; margin-bottom: 15px; }}
                .feature-item {{ display: flex; align-items: center; margin: 12px 0; color: #14171a; }}
                .feature-icon {{ width: 32px; height: 32px; background: linear-gradient(135deg, #1da1f2 0%, #0d8bd9 100%); border-radius: 8px; display: flex; align-items: center; justify-content: center; margin-right: 12px; color: white; font-size: 16px; }}
                .footer {{ background: #14171a; padding: 30px; text-align: center; color: #8899a6; font-size: 13px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📈 NeuroSight</h1>
                    <p>AI-Powered Financial Analytics Platform</p>
                </div>
                <div class="content">
                    <div class="welcome"><strong>Welcome, {name}! 🏆</strong></div>
                    <p style="color: #14171a; font-size: 16px; line-height: 1.6;">
                        Thank you for joining NeuroSight! To complete your registration and start exploring 
                        real-time market insights, please verify your email address.
                    </p>
                    <div class="code-box">
                        <p style="margin: 0; color: #14171a; font-size: 16px; font-weight: 600;">Your Verification Code</p>
                        <div class="code">{code}</div>
                        <p class="validity">⏰ Valid for 15 minutes</p>
                    </div>
                    <p class="info">
                        ⏰ <strong>Important:</strong> This code will expire in 15 minutes.
                    </p>
                    <div class="features">
                        <h3>🚀 What's Waiting for You:</h3>
                        <div class="feature-item">
                            <div class="feature-icon">📊</div>
                            <span><strong>Real-Time Market Data:</strong> Track AAPL, NVDA, TSLA, and more</span>
                        </div>
                        <div class="feature-item">
                            <div class="feature-icon">🤖</div>
                            <span><strong>AI-Powered Predictions:</strong> ML models for price forecasting</span>
                        </div>
                        <div class="feature-item">
                            <div class="feature-icon">💬</div>
                            <span><strong>Smart Chatbot:</strong> Get instant answers to financial queries</span>
                        </div>
                    </div>
                </div>
                <div class="footer">
                    <p style="margin-bottom: 10px;"><strong>NeuroSight</strong> - Your AI Trading Companion</p>
                    <p style="margin: 5px 0;">© 2026 NeuroSight. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Send email
        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            to=[{"email": email, "name": name}],
            sender={"email": SENDER_EMAIL, "name": SENDER_NAME},
            subject="🎉 Welcome to NeuroSight - Verify Your Email",
            html_content=html
        )
        
        api_response = api_instance.send_transac_email(send_smtp_email)
        print(f"✅ Verification email sent to {email} via Brevo")
        print(f"🏆 Check phone: {email}")
        return True
            
    except ApiException as e:
        if e.status == 401 and 'authorised_ips' in str(e.body):
            print(f"❌ Brevo IP NOT AUTHORIZED — go to https://app.brevo.com/security/authorised_ips and remove IP restrictions")
        else:
            print(f"❌ Brevo API error {e.status}: {e.body}")
        print(f"[FALLBACK] Verification code for {email}: {code}")
        return False
    except Exception as e:
        print(f"❌ Email error: {str(e)}")
        print(f"[FALLBACK] Verification code for {email}: {code}")
        return False

def send_welcome_email(email: str, name: str):
    """Send welcome email after verification"""
    
    if not BREVO_AVAILABLE or not BREVO_API_KEY:
        print(f"✅ Welcome email would be sent to {email}")
        return True
    
    try:
        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key['api-key'] = BREVO_API_KEY
        
        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background: #f5f8fa; }}
                .container {{ max-width: 600px; margin: 40px auto; background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 24px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #17bf63 0%, #14a854 100%); padding: 40px; text-align: center; }}
                .checkmark {{ width: 80px; height: 80px; background: white; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 48px; margin-bottom: 20px; }}
                .header h1 {{ color: white; margin: 0; font-size: 32px; font-weight: 700; }}
                .content {{ padding: 40px; text-align: center; }}
                .button {{ display: inline-block; background: linear-gradient(135deg, #1da1f2 0%, #0d8bd9 100%); color: white; padding: 16px 40px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 16px; margin: 20px 0; }}
                .footer {{ background: #14171a; padding: 30px; text-align: center; color: #8899a6; font-size: 13px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="checkmark">✅</div>
                    <h1>Account Verified!</h1>
                </div>
                <div class="content">
                    <h2 style="color: #14171a; margin: 0 0 20px 0;">Welcome to NeuroSight, {name}! 🎉</h2>
                    <p style="color: #657786; font-size: 16px; line-height: 1.6;">
                        Your email has been successfully verified. You're all set to start exploring!
                    </p>
                    <a href="{APP_BASE_URL}/login.html" class="button">Login to Dashboard</a>
                </div>
                <div class="footer">
                    <p>© 2026 NeuroSight. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            to=[{"email": email, "name": name}],
            sender={"email": SENDER_EMAIL, "name": SENDER_NAME},
            subject="✅ Your NeuroSight Account is Ready!",
            html_content=html
        )
        
        api_instance.send_transac_email(send_smtp_email)
        print(f"✅ Welcome email sent to {email}")
        return True
            
    except Exception as e:
        print(f"❌ Welcome email error: {str(e)}")
        return False

def store_verification_code(user_id: str, email: str, code: str):
    """Store verification code in Firestore"""
    try:
        # Ensure email is lowercase for consistency
        email_lower = email.lower().strip()
        now = datetime.now(timezone.utc)
        db.collection("verification_codes").document(email_lower).set({
            "user_id": user_id,
            "email": email_lower,
            "code": code,
            "created_at": now,
            "expires_at": now + timedelta(minutes=15),
            "verified": False
        })
        print(f"✅ Stored code '{code}' for {email_lower} (user_id: {user_id})")
        return True
    except Exception as e:
        print(f"❌ Failed to store code: {str(e)}")
        return False

def verify_code(email: str, code: str):
    """Verify the code"""
    try:
        # Ensure email is lowercase and trimmed
        email_lower = email.lower().strip()
        code_clean = re.sub(r"\D", "", code or "")[:6]
        
        codes_ref = db.collection("verification_codes")
        doc = codes_ref.document(email_lower).get()
        data = doc.to_dict() if doc.exists else None

        if not data:
            query = (
                codes_ref
                .where(filter=firestore.FieldFilter("email", "==", email_lower))
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(1)
            )
            docs = query.get()
            if not docs:
                print(f"❌ No verification code found for {email_lower}")
                return {"success": False, "message": "Invalid verification code"}
            doc = docs[0]
            data = doc.to_dict()
        
        print(f"🏆 Checking code: stored='{data['code']}' vs entered='{code_clean}'")
        
        if data["code"] != code_clean:
            print(f"❌ Code mismatch!")
            return {"success": False, "message": "Invalid verification code"}
        
        # Compare timezone-aware datetimes
        now = datetime.now(timezone.utc)
        expires_at = data.get("expires_at")
        if expires_at and getattr(expires_at, "tzinfo", None) is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at and now > expires_at:
            print(f"❌ Code expired at {data['expires_at']}")
            return {"success": False, "message": "Verification code has expired"}
        
        if data.get("verified", False):
            print(f"❌ Code already used")
            return {"success": False, "message": "Code has already been used"}
        
        doc.reference.update({"verified": True, "verified_at": datetime.now(timezone.utc)})
        print(f"✅ Code verified successfully for {email}")
        
        return {"success": True, "message": "Email verified successfully!"}
        
    except Exception as e:
        print(f"❌ Verification error: {str(e)}")
        return {"success": False, "message": "Verification failed"}

def send_password_reset_email(email: str, name: str, reset_code: str):
    """Send password reset email using Brevo"""
    
    print(f"🏆 Sending password reset email with code: {reset_code} to {email}")
    
    # Fallback if Brevo not configured
    if not BREVO_AVAILABLE or not BREVO_API_KEY:
        print(f"🏆 Password reset code for {email}: {reset_code}")
        return True
    
    try:
        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key['api-key'] = BREVO_API_KEY
        
        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background: #f5f8fa; }}
                .container {{ max-width: 600px; margin: 40px auto; background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 24px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #e0245e 0%, #c41e3a 100%); padding: 40px; text-align: center; }}
                .header h1 {{ color: white; margin: 0; font-size: 32px; }}
                .header p {{ color: rgba(255,255,255,0.9); margin: 10px 0 0 0; }}
                .content {{ padding: 40px; }}
                .greeting {{ font-size: 18px; color: #14171a; margin-bottom: 20px; }}
                .message {{ color: #14171a; font-size: 16px; line-height: 1.6; margin-bottom: 20px; }}
                .code-box {{ background: #fff4f4; border: 2px dashed #e0245e; border-radius: 12px; padding: 24px; text-align: center; margin: 30px 0; }}
                .code {{ font-size: 48px; font-weight: 700; letter-spacing: 8px; color: #e0245e; font-family: 'Courier New', monospace; }}
                .validity {{ color: #657786; font-size: 13px; margin-top: 10px; }}
                .warning {{ background: #fff4e6; border-left: 4px solid #ffad1f; padding: 16px; border-radius: 8px; color: #14171a; font-size: 14px; margin: 20px 0; }}
                .security-note {{ background: #f7f9fa; border-radius: 12px; padding: 20px; margin: 30px 0; }}
                .security-note h3 {{ color: #14171a; font-size: 18px; margin-bottom: 15px; }}
                .security-item {{ display: flex; align-items: start; margin: 12px 0; color: #14171a; font-size: 14px; line-height: 1.6; }}
                .security-icon {{ width: 24px; height: 24px; background: #e0245e; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin-right: 12px; color: white; font-size: 14px; flex-shrink: 0; margin-top: 2px; }}
                .footer {{ background: #14171a; padding: 30px; text-align: center; color: #8899a6; font-size: 13px; }}
                .btn {{ display: inline-block; background: linear-gradient(135deg, #e0245e 0%, #c41e3a 100%); color: white; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: 600; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🏆 NeuroSight</h1>
                    <p>Password Reset Request</p>
                </div>
                <div class="content">
                    <div class="greeting"><strong>Hello, {name}! 🏆</strong></div>
                    <p class="message">
                        We received a request to reset your NeuroSight account password. 
                        Use the code below to reset your password and regain access to your account.
                    </p>
                    <div class="code-box">
                        <p style="margin: 0; color: #14171a; font-size: 16px; font-weight: 600;">Your Password Reset Code</p>
                        <div class="code">{reset_code}</div>
                        <p class="validity">⏰ Valid for 15 minutes</p>
                    </div>
                    <p class="warning">
                        ⚠️ <strong>Important:</strong> This code expires in 15 minutes for your security.
                    </p>
                    <div class="security-note">
                        <h3>🏆 Security Tips:</h3>
                        <div class="security-item">
                            <div class="security-icon">🏆</div>
                            <span>If you didn't request this reset, ignore this email and your password will remain unchanged.</span>
                        </div>
                        <div class="security-item">
                            <div class="security-icon">🏆</div>
                            <span>Never share your reset code with anyone, including NeuroSight staff.</span>
                        </div>
                        <div class="security-item">
                            <div class="security-icon">🏆</div>
                            <span>Choose a strong, unique password with uppercase, lowercase, numbers, and special characters.</span>
                        </div>
                    </div>
                    <p class="message" style="color: #657786; font-size: 14px;">
                        If you continue to have issues accessing your account, please contact our support team.
                    </p>
                </div>
                <div class="footer">
                    <p style="margin-bottom: 10px;"><strong>NeuroSight</strong> - Your AI Trading Companion</p>
                    <p style="margin: 5px 0;">© 2026 NeuroSight. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            to=[{"email": email, "name": name}],
            sender={"email": SENDER_EMAIL, "name": SENDER_NAME},
            subject="🏆 Reset Your NeuroSight Password",
            html_content=html
        )
        
        api_response = api_instance.send_transac_email(send_smtp_email)
        print(f"✅ Password reset email sent to {email}")
        return True

    except ApiException as e:
        if e.status == 401 and 'authorised_ips' in str(e.body):
            print(f"❌ Brevo IP NOT AUTHORIZED — go to https://app.brevo.com/security/authorised_ips and remove IP restrictions")
        else:
            print(f"❌ Brevo API error {e.status}: {e.body}")
        print(f"[FALLBACK] Reset code for {email}: {reset_code}")
        return False
    except Exception as e:
        print(f"❌ Password reset email error: {str(e)}")
        print(f"[FALLBACK] Reset code for {email}: {reset_code}")
        return False

def store_password_reset_code(email: str, code: str):
    """Store password reset code in Firestore"""
    try:
        email_lower = email.lower().strip()
        now = datetime.now(timezone.utc)
        db.collection("password_resets").document(email_lower).set({
            "email": email_lower,
            "code": code,
            "created_at": now,
            "expires_at": now + timedelta(minutes=15),
            "used": False
        })
        print(f"✅ Stored reset code '{code}' for {email_lower}")
        return True
    except Exception as e:
        print(f"❌ Failed to store reset code: {str(e)}")
        return False

def verify_password_reset_code(email: str, code: str):
    """Verify password reset code"""
    try:
        email_lower = email.lower().strip()
        code_clean = code.strip()
        
        doc_ref = db.collection("password_resets").document(email_lower)
        doc = doc_ref.get()
        
        if not doc.exists:
            print(f"❌ No reset code found for {email_lower}")
            return {"success": False, "message": "Invalid reset code"}
        
        data = doc.to_dict()
        
        print(f"🏆 Checking reset code: stored='{data['code']}' vs entered='{code_clean}'")
        
        if data["code"] != code_clean:
            print(f"❌ Code mismatch!")
            return {"success": False, "message": "Invalid reset code"}
        
        now = datetime.now(timezone.utc)
        if now > data["expires_at"]:
            print(f"❌ Code expired")
            return {"success": False, "message": "Reset code has expired"}
        
        if data.get("used", False):
            print(f"❌ Code already used")
            return {"success": False, "message": "Reset code has already been used"}
        
        print(f"✅ Reset code verified for {email_lower}")
        return {"success": True, "message": "Code verified!"}
        
    except Exception as e:
        print(f"❌ Reset code verification error: {str(e)}")
        return {"success": False, "message": "Verification failed"}
