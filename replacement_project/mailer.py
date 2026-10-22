"""Optional unattended sending of factual warranty *policy* questions.

Never sends claims about defects, ownership, purchases, or entitlement.
Contacts must be explicitly checked and have a verified contact address.
"""
import os
import re
import smtplib
import ssl
import time
from email.message import EmailMessage
from .store import utcnow

EMAIL_RE = re.compile(r'^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$')


def prepared(con):
    """One recipient ever, including contacts marked pending/uncertain."""
    items = con.execute('''SELECT m.id, m.name, m.category, lower(trim(m.contact_email)) AS recipient
       FROM manufacturers m
       WHERE m.research_status='checked' AND trim(m.contact_email)!=''
       AND NOT EXISTS (SELECT 1 FROM policy_outreach p WHERE p.recipient=lower(trim(m.contact_email)))
       ORDER BY m.name''').fetchall()
    seen = set()
    result = []
    for row in items:
        if row['recipient'] in seen or not EMAIL_RE.fullmatch(row['recipient']):
            continue
        seen.add(row['recipient'])
        result.append(row)
    return result


def compose(company, category):
    subject = 'Warranty policy question: ' + company
    kind = (' for ' + category.lower()) if category.strip() else ''
    body = (f'Hello {company} Support,\n\n'
            f'I am researching your warranty policy{kind}. '
            'Could you clarify the warranty coverage requirements, whether proof of purchase is normally needed, '
            'and the best way to submit an eligible product for evaluation?\n\n'
            'Thank you for your guidance.')
    return subject, body


def send_policy_inquiries(con, sender, password, limit=3, delay=30, smtp_factory=None, sleeper=time.sleep):
    if not 1 <= limit <= 20:
        raise ValueError('Limit must be between 1 and 20')
    if delay < 0:
        raise ValueError('Delay cannot be negative')
    if not EMAIL_RE.fullmatch(sender):
        raise ValueError('Set a valid GMAIL_ADDRESS environment variable')
    if not password:
        raise ValueError('Set GMAIL_APP_PASSWORD environment variable')
    ready = prepared(con)[:limit]
    if not ready:
        return 0
    factory = smtp_factory or smtplib.SMTP_SSL
    sent = 0
    with factory('smtp.gmail.com',465,context=ssl.create_default_context(),timeout=30) as smtp:
        smtp.login(sender,password)
        for index,row in enumerate(ready):
            subject, body = compose(row['name'],row['category'])
            # Mark pending before the attempt. If process crashes, there is no automatic retry.
            cursor = con.execute('''INSERT OR IGNORE INTO policy_outreach
                        (manufacturer_id,recipient,subject,state,updated_at)
                        VALUES (?,?,?,'pending',?)''',
                        (row['id'],row['recipient'],subject,utcnow()))
            con.commit()
            if cursor.rowcount == 0:
                continue
            msg = EmailMessage()
            msg['From'] = sender
            msg['To'] = row['recipient']
            msg['Subject'] = subject
            msg.set_content(body)
            try:
                smtp.send_message(msg)
            except (OSError,smtplib.SMTPException):
                # Delivery is uncertain: never automatically resend this recipient.
                con.execute("UPDATE policy_outreach SET state='uncertain',updated_at=? WHERE recipient=?", (utcnow(),row['recipient']))
                con.commit()
                raise
            else:
                con.execute("UPDATE policy_outreach SET state='sent',updated_at=? WHERE recipient=?", (utcnow(),row['recipient']))
                con.commit()
                sent += 1
                print('Sent policy inquiry to',row['name'])
            if index < len(ready)-1:
                sleeper(delay)
    return sent
