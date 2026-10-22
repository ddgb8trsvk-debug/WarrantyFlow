"""Private local SQLite storage for WarrantyFlow."""
import csv
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PATH = Path.home() / '.warrantyflow' / 'warrantyflow.sqlite3'
CASE_STATUSES = ('draft', 'researching', 'ready', 'submitted', 'awaiting_reply', 'resolved', 'closed')
RESEARCH_STATES = ('unverified', 'needs_recheck', 'checked')


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


@contextmanager
def database(path=DEFAULT_PATH):
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=10)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys = ON')
    con.executescript('''
        CREATE TABLE IF NOT EXISTS manufacturers (
          id INTEGER PRIMARY KEY,
          name TEXT NOT NULL UNIQUE COLLATE NOCASE,
          category TEXT NOT NULL DEFAULT '',
          policy_url TEXT NOT NULL DEFAULT '',
          contact_url TEXT NOT NULL DEFAULT '',
          contact_email TEXT NOT NULL DEFAULT '',
          proof_requirement TEXT NOT NULL DEFAULT '',
          research_status TEXT NOT NULL DEFAULT 'unverified',
          notes TEXT NOT NULL DEFAULT '',
          verified_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS cases (
          id INTEGER PRIMARY KEY,
          manufacturer_id INTEGER REFERENCES manufacturers(id),
          product_name TEXT NOT NULL,
          issue TEXT NOT NULL,
          purchase_info TEXT NOT NULL DEFAULT '',
          proof_available INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'draft',
          notes TEXT NOT NULL DEFAULT '',
          follow_up_on TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS activity (
          id INTEGER PRIMARY KEY,
          case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
          event TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS policy_outreach (
          id INTEGER PRIMARY KEY,
          manufacturer_id INTEGER NOT NULL REFERENCES manufacturers(id),
          recipient TEXT NOT NULL COLLATE NOCASE UNIQUE,
          subject TEXT NOT NULL,
          state TEXT NOT NULL CHECK(state IN ('pending','sent','uncertain')),
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status);
        CREATE INDEX IF NOT EXISTS idx_activity_case ON activity(case_id);
    ''')
    con.commit()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def manufacturers(con, term=''):
    q = '%' + term.strip() + '%'
    return con.execute('SELECT * FROM manufacturers WHERE name LIKE ? OR category LIKE ? ORDER BY name', (q, q)).fetchall()


def get_manufacturer(con, manufacturer_id):
    return con.execute('SELECT * FROM manufacturers WHERE id=?', (manufacturer_id,)).fetchone()


def add_manufacturer(con, name, category='', policy_url='', contact_url='', contact_email='', proof_requirement='', research_status='unverified', notes='', verified_at=''):
    name = name.strip()
    if not name:
        raise ValueError('Manufacturer name is required')
    if research_status not in RESEARCH_STATES:
        raise ValueError('Invalid research status')
    con.execute('''INSERT INTO manufacturers
       (name,category,policy_url,contact_url,contact_email,proof_requirement,research_status,notes,verified_at)
       VALUES (?,?,?,?,?,?,?,?,?)
       ON CONFLICT(name) DO UPDATE SET
       category=CASE WHEN excluded.category!='' THEN excluded.category ELSE manufacturers.category END,
       policy_url=CASE WHEN excluded.policy_url!='' THEN excluded.policy_url ELSE manufacturers.policy_url END,
       contact_url=CASE WHEN excluded.contact_url!='' THEN excluded.contact_url ELSE manufacturers.contact_url END,
       contact_email=CASE WHEN excluded.contact_email!='' THEN excluded.contact_email ELSE manufacturers.contact_email END,
       proof_requirement=CASE WHEN excluded.proof_requirement!='' THEN excluded.proof_requirement ELSE manufacturers.proof_requirement END,
       notes=CASE WHEN excluded.notes!='' THEN excluded.notes ELSE manufacturers.notes END
    ''', (name, category, policy_url, contact_url, contact_email, proof_requirement, research_status, notes, verified_at))


def cases(con, term='', status=''):
    q = '%' + term.strip() + '%'
    sql = '''SELECT c.*, m.name AS company, m.contact_url, m.policy_url, m.proof_requirement,
                    m.research_status, m.contact_email
             FROM cases c LEFT JOIN manufacturers m ON c.manufacturer_id=m.id
             WHERE (c.product_name LIKE ? OR c.issue LIKE ? OR coalesce(m.name,'') LIKE ?)'''
    args = [q, q, q]
    if status:
        if status not in CASE_STATUSES:
            raise ValueError('Invalid status')
        sql += ' AND c.status=?'
        args.append(status)
    return con.execute(sql + ' ORDER BY c.updated_at DESC, c.id DESC', args).fetchall()


def get_case(con, case_id):
    return con.execute('''SELECT c.*, m.name AS company, m.policy_url, m.contact_url,
              m.proof_requirement, m.research_status, m.contact_email
              FROM cases c LEFT JOIN manufacturers m ON c.manufacturer_id=m.id
              WHERE c.id=?''', (case_id,)).fetchone()


def create_case(con, manufacturer_id, product_name, issue, purchase_info='', proof_available=False, notes=''):
    if not product_name.strip() or not issue.strip():
        raise ValueError('Product name and issue are required')
    if manufacturer_id is not None and get_manufacturer(con, manufacturer_id) is None:
        raise ValueError('Unknown manufacturer')
    now = utcnow()
    cursor = con.execute('''INSERT INTO cases
      (manufacturer_id,product_name,issue,purchase_info,proof_available,status,notes,created_at,updated_at)
      VALUES (?,?,?,?,?,?,?,?,?)''',
      (manufacturer_id, product_name.strip(), issue.strip(), purchase_info.strip(), int(bool(proof_available)), 'draft', notes.strip(), now, now))
    add_activity(con, cursor.lastrowid, 'Case created')
    return cursor.lastrowid


def add_activity(con, case_id, event):
    con.execute('INSERT INTO activity (case_id,event,created_at) VALUES (?,?,?)',
                (case_id, event[:500], utcnow()))


def activity(con, case_id):
    return con.execute('SELECT * FROM activity WHERE case_id=? ORDER BY id DESC', (case_id,)).fetchall()


def edit_case(con, case_id, status, notes, follow_up_on=''):
    if status not in CASE_STATUSES:
        raise ValueError('Invalid case status')
    if follow_up_on:
        try:
            datetime.strptime(follow_up_on, '%Y-%m-%d')
        except ValueError:
            raise ValueError('Follow-up date must be YYYY-MM-DD')
    prior = get_case(con, case_id)
    if prior is None:
        raise ValueError('Unknown case')
    con.execute('UPDATE cases SET status=?, notes=?, follow_up_on=?, updated_at=? WHERE id=?',
                (status, notes.strip(), follow_up_on, utcnow(), case_id))
    if prior['status'] != status:
        add_activity(con, case_id, 'Status: ' + prior['status'] + ' to ' + status)
    if prior['notes'] != notes.strip() or prior['follow_up_on'] != follow_up_on:
        add_activity(con, case_id, 'Case notes or follow-up updated')


def import_research(con, path):
    """Import company reference records. Never import old fictional claims or contact data as verified."""
    with Path(path).open(newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or 'Company' not in reader.fieldnames:
            raise ValueError('CSV must contain a Company column')
        count = 0
        for row in reader:
            name = (row.get('Company') or '').strip()
            if not name:
                continue
            notes = (row.get('Research Notes') or '').strip()
            policy = (row.get('Warranty Policy') or '').strip()
            if policy:
                notes = ('Previously recorded policy summary: ' + policy + '\n' + notes).strip()
            verified = (row.get('Verified On') or '').strip()
            if verified:
                notes = (notes + '\nResearch dated: ' + verified).strip()
            # Old sources may be stale. Never call them independently verified.
            add_manufacturer(con, name, category=(row.get('Product') or '').strip(),
                policy_url=(row.get('Source URL') or '').strip(),
                contact_url=(row.get('Contact URL') or '').strip(),
                proof_requirement=(row.get('Proof of Purchase') or '').strip(),
                research_status='needs_recheck', notes=notes)
            count += 1
        return count


def stats(con):
    return {
        'manufacturers': con.execute('SELECT COUNT(*) FROM manufacturers').fetchone()[0],
        'cases': con.execute('SELECT COUNT(*) FROM cases').fetchone()[0],
        'open_cases': con.execute("SELECT COUNT(*) FROM cases WHERE status NOT IN ('resolved','closed')").fetchone()[0],
        'resolved': con.execute("SELECT COUNT(*) FROM cases WHERE status='resolved'").fetchone()[0],
        'needs_recheck': con.execute("SELECT COUNT(*) FROM manufacturers WHERE research_status='needs_recheck'").fetchone()[0],
        'policy_inquiries_sent': con.execute("SELECT COUNT(*) FROM policy_outreach WHERE state='sent'").fetchone()[0],
    }


def export_cases(con, path):
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    columns = ('id','company','product_name','issue','purchase_info','proof_available','status','notes','follow_up_on','created_at','updated_at')
    items = cases(con)
    with p.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for r in items:
            writer.writerow([r[col] for col in columns])
    return len(items)


def due_followups(con, on_date=None):
    """List overdue or due-today open cases in follow-up order."""
    today = on_date or datetime.now(timezone.utc).date().isoformat()
    return con.execute("""SELECT c.*, m.name AS company FROM cases c
       LEFT JOIN manufacturers m ON m.id=c.manufacturer_id
       WHERE c.follow_up_on != '' AND c.follow_up_on <= ?
       AND c.status NOT IN ('resolved','closed')
       ORDER BY c.follow_up_on ASC""", (today,)).fetchall()
