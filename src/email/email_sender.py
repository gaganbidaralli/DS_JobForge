"""Send job application emails via Gmail SMTP."""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from email.mime.base      import MIMEBase
from email                import encoders
from pathlib              import Path
from config.settings      import settings

EMAIL_TEMPLATES = {
    "professional": """\
Dear Hiring Team,

Please find attached my application for the {position} role at {company}.
I have included my tailored resume and cover letter for your consideration.

I am confident that my skills and experience make me a strong candidate,
and I would welcome the opportunity to discuss how I can contribute to your team.

Thank you for your time and consideration.

Best regards,
{name}
""",
    "enthusiastic": """\
Dear Hiring Team,

I am thrilled to apply for the {position} position at {company}!
Attached you will find my resume and cover letter, both crafted specifically for this role.

I would love to bring my skills to your team and am excited about this opportunity.

Thank you so much for considering my application!

With enthusiasm,
{name}
""",
    "concise": """\
Hi,

Please find my application for {position} at {company} attached.

I look forward to hearing from you.

{name}
""",
}


class EmailSender:

    def __init__(self, sender_email: str | None = None, sender_password: str | None = None):
        self.sender_email    = sender_email    or settings.EMAIL_ADDRESS
        self.sender_password = sender_password or settings.EMAIL_PASSWORD
        if not self.sender_email or not self.sender_password:
            raise ValueError(
                "Email credentials not configured. Set EMAIL_ADDRESS and EMAIL_PASSWORD in .env"
            )

    def send_application(
        self,
        recipient_email: str,
        company:         str,
        position:        str,
        applicant_name:  str,
        resume_path:     str | Path,
        cover_letter_path: str | Path | None = None,
        cc_email:        str | None = None,
        template:        str = "professional",
    ) -> bool:
        msg = MIMEMultipart()
        msg["From"]    = self.sender_email
        msg["To"]      = recipient_email
        msg["Subject"] = f"Application: {position} — {applicant_name}"
        if cc_email:
            msg["Cc"] = cc_email

        body_tpl = EMAIL_TEMPLATES.get(template, EMAIL_TEMPLATES["professional"])
        body     = body_tpl.format(position=position, company=company, name=applicant_name)
        msg.attach(MIMEText(body, "plain"))

        self._attach_file(msg, Path(resume_path))
        if cover_letter_path and Path(cover_letter_path).exists():
            self._attach_file(msg, Path(cover_letter_path))

        recipients = [recipient_email]
        if cc_email:
            recipients.append(cc_email)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(self.sender_email, self.sender_password)
            server.sendmail(self.sender_email, recipients, msg.as_string())

        return True

    def _attach_file(self, msg: MIMEMultipart, path: Path):
        with open(path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={path.name}")
        msg.attach(part)
