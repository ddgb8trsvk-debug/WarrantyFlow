"""WarrantyFlow command-line interface (standard library only)."""
import argparse
import csv
import os
import smtplib
import ssl
import tempfile
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

FIELDS = ['Company', 'Product', 'Contact Email', 'Policy URL', 'Question', 'Status', 'Sent At']
DEFAULT_DB = Path('data/inquiries.csv')
SAMPLE = [
    ('JanSport', 'Backpacks', 'https://www.jansport.com/customer-service/warranty.html'),
    ('Nalgene', 'Water bottles', 'https://nalgene.com/'),
    ('CamelBak', 'Hydration products', 'https://www.camelbak.com/'),
    ('Darn Tough', 'Socks', 'https://darntough.com/pages/our-unconditional-lifetime-guarantee'),
    ('Leatherman', 'Multitools', 'https://www.leatherman.com/'),
]

def read_db(path):
    if not path.exists():
        raise SystemExit(f'Database not found: {path}. Run: python3 app.py init')
    with path.open(newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not set(FIELDS).issubset(reader.fieldnames):
            raise SystemExit('Invalid database columns. Expected: ' + ', '.join(FIELDS))
        return list(reader)

def save_db(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.warrantyflow-', suffix='.csv', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def init(path):
    if path.exists():
        print(f'Already exists: {path}. No changes made.')
        return
    rows = [dict(zip(FIELDS, [company, product, '', url, '', 'research', ''])) for company, product, url in SAMPLE]
    save_db(path, rows)
    print(f'Created {path} with {len(rows)} example research entries.')

def draft(row):
    company = row['Company'].strip()
    product = row['Product'].strip()
    question = row['Question'].strip()
    subject = f'Warranty policy question: {product}'
    body = (f'Hello {company} Support,\n\n'
            f'I am researching your warranty coverage for {product.lower()}. '
            'Could you clarify the eligibility requirements, whether proof of purchase is necessary, '
            'and how a customer should request an evaluation?\n')
    if question:
        body += f'\nAdditional question: {question}\n'
    body += '\nThank you for your guidance.\n'
    return subject, body

def eligible(rows):
    seen = set()
    for row in rows:
        address = row['Contact Email'].strip().lower()
        if row['Status'].strip().lower() != 'ready' or not address or address.count('@') != 1:
            continue
        if address in seen:
            continue
        seen.add(address)
        yield row

def send_one(row, sender, password):
    subject, body = draft(row)
    msg = EmailMessage()
    msg['From'] = sender
    msg['To'] = row['Contact Email'].strip()
    msg['Subject'] = subject
    msg.set_content(body)
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=ssl.create_default_context(), timeout=30) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)

def main(argv=None):
    parser = argparse.ArgumentParser(description='WarrantyFlow: warranty policy research and email workflow')
    parser.add_argument('--db', type=Path, default=DEFAULT_DB, help='CSV database path')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('init', help='Create a sample research database')
    commands.add_parser('list', help='List all companies')
    commands.add_parser('report', help='Show database summary')
    commands.add_parser('preview', help='Show messages that would be sent')
    send = commands.add_parser('send', help='Send ready factual policy inquiries (no per-email prompts)')
    send.add_argument('--limit', type=int, default=10, help='Maximum messages per run (default 10)')
    args = parser.parse_args(argv)
    if args.command == 'init':
        init(args.db)
        return
    rows = read_db(args.db)
    if args.command == 'list':
        for index, row in enumerate(rows, 1):
            print(f"{index:>3}. {row['Company']} | {row['Status']} | {row['Contact Email'] or '(no contact)'}")
    elif args.command == 'report':
        print(f'Companies: {len(rows)}')
        for status in sorted(set(r['Status'].strip().lower() for r in rows)):
            print(f'{status or "unset"}: {sum(r["Status"].strip().lower() == status for r in rows)}')
        print(f'Ready with unique recipients: {len(list(eligible(rows)))}')
    elif args.command == 'preview':
        ready = list(eligible(rows))
        if not ready:
            print('No ready inquiries. No emails sent.')
        for row in ready:
            subject, body = draft(row)
            print(f"\nTo: {row['Contact Email']}\nSubject: {subject}\n\n{body}")
    elif args.command == 'send':
        if args.limit < 1 or args.limit > 50:
            parser.error('--limit must be between 1 and 50')
        ready = list(eligible(rows))[:args.limit]
        if not ready:
            print('No ready inquiries. No emails sent.')
            return
        sender = os.environ.get('GMAIL_ADDRESS', '').strip()
        password = os.environ.get('GMAIL_APP_PASSWORD', '').replace(' ', '')
        if not sender or not password:
            raise SystemExit('Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD environment variables first.')
        count = 0
        for row in ready:
            try:
                send_one(row, sender, password)
            except (OSError, smtplib.SMTPException) as exc:
                print(f'Sending stopped after {count} successful messages: {type(exc).__name__}: {exc}')
                return
            row['Status'] = 'sent'
            row['Sent At'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
            save_db(args.db, rows)
            count += 1
            print(f"Sent to {row['Company']}")
        print(f'Complete: {count} sent.')

if __name__ == '__main__':
    main()
