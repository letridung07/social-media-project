from flask import render_template, current_app
from flask_mail import Message
from app import mail # Assuming mail is initialized in app and can be imported

def send_password_reset_email(user_email, username, reset_url):
    try:
        msg = Message(
            subject="Password Reset Request",
            sender=current_app.config.get('MAIL_DEFAULT_SENDER'),
            recipients=[user_email]
        )
        msg.body = f'''Dear {username},

To reset your password, please visit the following link:
{reset_url}

If you did not make this request then simply ignore this email and no changes will be made.

Sincerely,
The Team
'''
        # For HTML emails, you could use render_template for msg.html
        # msg.html = render_template('email/reset_password.html', username=username, reset_url=reset_url)

        mail.send(msg)
        return True
    except Exception as e:
        # Log the error for debugging purposes
        # It's important to not expose too much detail to the user for security reasons
        current_app.logger.error(f"Failed to send password reset email to {user_email}: {str(e)}")
        return False
