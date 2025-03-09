import smtplib
import logging
from email.mime.text import MIMEText
from config import EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER, SPREADSHEET_ID

# Google Sheets link
SHEET_LINK = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}"

# Setup logging
logging.basicConfig(filename="logs/email.log", level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def send_email_notification():
    """Send an email notification when translations are ready for review."""
    subject = "🚀 Translation Review Needed: AD CREATIVES"
    body = f"Hello,\n\nNew translations are ready for review.\n\nPlease check the spreadsheet: {SHEET_LINK}\n\nBest,\nYour Automation Bot"

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        logging.info("✅ Email notification sent successfully.")
        print("✅ Email sent successfully.")
    except Exception as e:
        logging.error(f"❌ Failed to send email: {str(e)}")
        print(f"❌ Failed to send email: {str(e)}")

if __name__ == "__main__":
    send_email_notification()
