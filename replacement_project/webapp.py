"""A single-user, localhost-only browser dashboard using the Python standard library."""
from datetime import date
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlsplit
import secrets
import webbrowser

from . import store

CSS = '''
:root{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;color:#18232d;background:#f5f7fb}
*{box-sizing:border-box}body{margin:0}a{color:#165b9d;text-decoration:none}a:hover{text-decoration:underline}
header{background:#12253b;color:white;padding:17px max(24px,calc((100vw - 1100px)/2));display:flex;align-items:center;gap:24px;flex-wrap:wrap}
header strong{font-size:22px;letter-spacing:-.4px}nav{display:flex;gap:16px}nav a{color:#dceaf6;font-size:14px}
main{max-width:1100px;padding:28px 20px 60px;margin:auto}h1{font-size:29px;margin:0 0 10px}h2{font-size:20px;margin:12px 0}p{line-height:1.55}small,.muted{color:#607286}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(185px,1fr));gap:14px;margin:18px 0}.tile,.panel{background:white;border:1px solid #e4eaf1;border-radius:13px;padding:20px;box-shadow:0 2px 12px #20344a06}.tile .num{font-weight:750;font-size:32px;margin-top:8px}
.panel{margin:20px 0}.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:18px 0}input,select,textarea{font:inherit;border:1px solid #cbd5e0;border-radius:8px;padding:10px 12px;background:white;width:100%;color:#18232d}input[type=checkbox]{width:auto}input[type=date]{width:auto}input:focus,textarea:focus,select:focus{outline:2px solid #abcbe8}textarea{min-height:92px;resize:vertical}label{display:block;font-size:13px;font-weight:650;margin:14px 0 6px}.fieldrow{display:grid;grid-template-columns:repeat(auto-fit,minmax(235px,1fr));gap:14px}
button,.btn{display:inline-block;border-radius:8px;padding:10px 15px;background:#155a96;color:#fff;border:1px solid #155a96;font-weight:600;cursor:pointer;font-size:14px;text-decoration:none}button:hover,.btn:hover{background:#104677;color:white;text-decoration:none}.secondary{background:white;color:#155a96;border-color:#b6cbe0}.secondary:hover{background:#ebf3fb;color:#104677}.danger{background:#9c3232}
table{width:100%;border-collapse:collapse;font-size:14px}th{text-align:left;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:#5e7389}td,th{padding:13px 10px;border-bottom:1px solid #edf0f4;vertical-align:top}tr:last-child td{border-bottom:0}td{line-height:1.45}.scroll{overflow:auto}
.tag{display:inline-block;border-radius:20px;background:#eaf1f8;color:#2b4e72;padding:4px 9px;font-size:12px;font-weight:650}.tag.good{background:#e3f6ec;color:#1b6d45}.tag.warn{background:#fff3d9;color:#855a05}
.notice{padding:14px;border-radius:9px;background:#eef6fc;color:#244f73;margin:18px 0}.error{background:#fff0f0;color:#943838}.meta{margin:9px 0;color:#607286}.mono{font-family:ui-monospace,monospace;white-space:pre-wrap;background:#f6f8fb;border:1px solid #e6eaf0;padding:14px;border-radius:8px;overflow-wrap:anywhere}.footer{text-align:center;margin-top:35px;font-size:13px;color:#68788a}
@media(max-width:680px){header{padding:16px 20px}nav{width:100%}main{padding:22px 14px}table{min-width:550px}}
'''


def esc(value):
    return escape(str(value if value is not None else ''), quote=True)


def safe_url(url):
    url = (url or '').strip()
    return url if urlsplit(url).scheme in ('http', 'https') and urlsplit(url).netloc else ''


def pill(value):
    text = (value or 'unknown').replace('_', ' ')
    cl = 'good' if value in ('resolved', 'checked') else ('warn' if value in ('needs_recheck', 'awaiting_reply') else '')
    return f'<span class="tag {cl}">{esc(text)}</span>'


def layout(title, body):
    nav = '<nav><a href="/">Overview</a><a href="/manufacturers">Manufacturers</a><a href="/cases">My cases</a><a href="/new">Add product</a><a href="/help">Help</a></nav>'
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} | WarrantyFlow</title><style>{CSS}</style></head>'
            f'<body><header><strong>WarrantyFlow</strong>{nav}</header><main>{body}<div class="footer">Runs on this computer only. Private cases stay outside your GitHub repository.</div></main></body></html>').encode('utf-8')


def form_token(token):
    return f'<input type="hidden" name="token" value="{esc(token)}">'


def case_table(rows):
    if not rows:
        return '<p class="muted">No cases yet. Add a product to begin tracking a real warranty issue.</p>'
    out = ['<div class="scroll"><table><thead><tr><th>Product</th><th>Manufacturer</th><th>Status</th><th>Follow-up</th></tr></thead><tbody>']
    for row in rows:
        out.append(f'<tr><td><a href="/case?id={row["id"]}"><strong>{esc(row["product_name"])}</strong></a><br><small>{esc(row["issue"][:90])}</small></td><td>{esc(row["company"] or "Unknown")}</td><td>{pill(row["status"])}</td><td>{esc(row["follow_up_on"] or "Not set")}</td></tr>')
    return ''.join(out) + '</tbody></table></div>'


def manufacturer_table(rows):
    if not rows:
        return '<p>No manufacturers match this search.</p>'
    out = ['<div class="scroll"><table><thead><tr><th>Company</th><th>Category</th><th>Research</th><th>Policy</th></tr></thead><tbody>']
    for row in rows:
        url = safe_url(row['policy_url'] or row['contact_url'])
        link = f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">Open official link ↗</a>' if url else '<span class="muted">No link</span>'
        out.append(f'<tr><td><a href="/manufacturer?id={row["id"]}"><strong>{esc(row["name"])}</strong></a></td><td>{esc(row["category"])}</td><td>{pill(row["research_status"])}</td><td>{link}</td></tr>')
    return ''.join(out) + '</tbody></table></div>'


def draft_text(row):
    """Uses only real details entered by the user, never hypothetical dataset claims."""
    manufacturer = row['company'] or 'Customer Support'
    product = row['product_name']
    issue = row['issue']
    subject = 'Warranty evaluation inquiry: ' + product
    body = (f'Hello {manufacturer} Support,\n\n'
            f'I would like to ask about the warranty evaluation process for my {product}. '
            f'The issue I have recorded is: {issue}\n\n'
            'Could you confirm whether this type of issue may qualify for warranty evaluation, '
            'what documentation is required, and whether the product needs to be inspected or returned?\n\n'
            'Thank you for your guidance.')
    return subject, body


class Handler(BaseHTTPRequestHandler):
    db_path = store.DEFAULT_PATH
    token = ''

    def log_message(self, format, *args):
        # Avoid recording case details or query strings in local server logs.
        pass

    def page(self, title, content, status=200):
        data = layout(title, content)
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, where):
        self.send_response(303)
        self.send_header('Location', where)
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()

    def query(self):
        return parse_qs(urlsplit(self.path).query)

    def q(self, name, default=''):
        return self.query().get(name, [default])[0]

    def fail(self, message, status=400):
        self.page('Problem', f'<h1>Could not complete the request</h1><div class="notice error">{esc(message)}</div><a href="/">Back to overview</a>', status)

    def do_GET(self):
        try:
            path = urlsplit(self.path).path
            with store.database(self.db_path) as con:
                if path == '/':
                    st = store.stats(con)
                    numbers = [('Manufacturers', st['manufacturers']), ('Products tracked', st['cases']), ('Open cases', st['open_cases']), ('Resolved', st['resolved'])]
                    tiles = ''.join(f'<div class="tile"><span class="muted">{esc(label)}</span><div class="num">{n}</div></div>' for label,n in numbers)
                    items = store.cases(con)[:8]
                    due = store.due_followups(con)
                    body = '<h1>Warranty organizer</h1><p class="muted">Research warranty policies, track actual products, and manage claims in one place.</p>'
                    body += f'<div class="grid">{tiles}</div><div class="toolbar"><a class="btn" href="/new">+ Add a product</a><a class="btn secondary" href="/manufacturers">Browse manufacturers</a></div>'
                    if st['needs_recheck']:
                        body += f'<div class="notice">{st["needs_recheck"]} imported policy records are marked for rechecking. Always verify the current manufacturer policy before submitting a claim.</div>'
                    if due:
                        body += '<div class="panel"><h2>Follow-ups due (' + str(len(due)) + ')</h2>' + case_table(due[:8]) + '</div>'
                    body += '<div class="panel"><h2>Recent cases</h2>' + case_table(items) + '</div>'
                    self.page('Overview', body)
                elif path == '/manufacturers':
                    term = self.q('q')
                    body = '<h1>Manufacturer research</h1><p class="muted">Reference information is not a guarantee of warranty coverage.</p><p><a class="btn secondary" href="/manufacturer-new">+ Add manufacturer</a></p>'
                    body += f'<form class="toolbar" method="get"><input style="max-width:380px" name="q" placeholder="Search brands or categories" value="{esc(term)}"><button>Search</button></form>'
                    body += '<div class="panel">' + manufacturer_table(store.manufacturers(con, term)) + '</div>'
                    self.page('Manufacturers', body)
                elif path == '/manufacturer-new':
                    body = f'''<h1>Add a manufacturer</h1><div class="panel"><form method="post" action="/add-manufacturer">{form_token(self.token)}
                       <label>Manufacturer name</label><input name="name" required maxlength="150">
                       <label>Product category</label><input name="category" maxlength="150" placeholder="e.g. kitchen appliances">
                       <label>Official policy URL (optional)</label><input name="policy_url" placeholder="https://...">
                       <label>Contact URL (optional)</label><input name="contact_url" placeholder="https://...">
                       <button>Add manufacturer</button></form></div>'''
                    self.page('Add manufacturer', body)
                elif path == '/manufacturer':
                    m = store.get_manufacturer(con, int(self.q('id', '0')))
                    if not m:
                        return self.fail('Unknown manufacturer', 404)
                    body = f'<h1>{esc(m["name"])}</h1><p>{pill(m["research_status"])}</p><div class="panel">'
                    for label, field in [('Category','category'), ('Proof of purchase','proof_requirement'), ('Research notes','notes'), ('Contact email','contact_email')]:
                        body += f'<p><strong>{esc(label)}:</strong> {esc(m[field]) or "Not recorded"}</p>'
                    for label, field in [('Warranty policy','policy_url'),('Contact information','contact_url')]:
                        link = safe_url(m[field]); body += f'<p><strong>{label}:</strong> ' + (f'<a href="{esc(link)}" target="_blank" rel="noopener noreferrer">Open official website ↗</a>' if link else 'Not recorded') + '</p>'
                    body += '</div>'
                    body += f'''<div class="panel"><h2>Update research record</h2><form method="post" action="/update-manufacturer">{form_token(self.token)}<input type="hidden" name="id" value="{m['id']}">
                        <label>Research status</label><select name="research_status">''' + ''.join(f'<option value="{esc(x)}" {"selected" if m["research_status"]==x else ""}>{esc(x.replace("_", " "))}</option>' for x in store.RESEARCH_STATES) + '</select>'
                    body += f'<label>Verified contact email (optional)</label><input type="email" name="contact_email" value="{esc(m["contact_email"])}" placeholder="support@example.com">'
                    body += f'<label>Contact URL</label><input name="contact_url" value="{esc(m["contact_url"])}">'
                    body += '<p class="muted">Mark checked only after reviewing the official policy yourself.</p><button>Save research details</button></form></div>'
                    self.page(m['name'], body)
                elif path == '/cases':
                    term = self.q('q'); status = self.q('status')
                    if status not in ('',) + store.CASE_STATUSES:
                        status = ''
                    body = '<h1>My warranty cases</h1><div class="toolbar"><a class="btn" href="/new">+ Add a product</a></div>'
                    body += f'<form class="toolbar" method="get"><input style="max-width:350px" name="q" placeholder="Search products or issues" value="{esc(term)}"><select style="max-width:200px" name="status"><option value="">All statuses</option>'
                    body += ''.join(f'<option value="{esc(x)}" {"selected" if x==status else ""}>{esc(x.replace("_", " "))}</option>' for x in store.CASE_STATUSES)
                    body += '</select><button>Filter</button></form><div class="panel">' + case_table(store.cases(con, term, status)) + '</div>'
                    self.page('My cases', body)
                elif path == '/new':
                    options = ''.join(f'<option value="{m["id"]}">{esc(m["name"])}</option>' for m in store.manufacturers(con))
                    body = f'''<h1>Add a product</h1><p class="muted">Only enter products and issues you actually have. Nothing is emailed automatically from this form.</p>
                       <div class="panel"><form method="post" action="/add-case">{form_token(self.token)}
                       <label>Manufacturer</label><select name="manufacturer_id" required><option value="">Choose a manufacturer</option>{options}</select>
                       <label>Product name or model</label><input name="product_name" required maxlength="180" placeholder="e.g. SuperBreak backpack">
                       <label>What is wrong with it?</label><textarea name="issue" required maxlength="2000" placeholder="Describe what you observed"></textarea>
                       <label>Purchase information (optional)</label><input name="purchase_info" maxlength="500" placeholder="Approximate date, shop, or order details">
                       <label><input type="checkbox" name="proof_available" value="1"> I have a receipt or other supporting evidence</label>
                       <label>Notes (optional)</label><textarea name="notes" maxlength="3000"></textarea>
                       <button>Add case</button></form></div>'''
                    self.page('Add product', body)
                elif path == '/case':
                    row = store.get_case(con, int(self.q('id', '0')))
                    if not row:
                        return self.fail('Unknown case', 404)
                    contact = safe_url(row['contact_url']); policy = safe_url(row['policy_url'])
                    links = ' · '.join(f'<a target="_blank" rel="noopener noreferrer" href="{esc(link)}">{label} ↗</a>' for label,link in [('Official warranty policy',policy),('Contact page',contact)] if link)
                    body = f'<h1>{esc(row["product_name"])}</h1><p class="meta">{esc(row["company"] or "Unknown")} · {pill(row["status"])}</p>'
                    body += f'<div class="panel"><h2>Issue</h2><p>{esc(row["issue"])}</p><p><strong>Purchase information:</strong> {esc(row["purchase_info"]) or "Not provided"}</p><p><strong>Evidence available:</strong> {"Yes" if row["proof_available"] else "Not marked"}</p><p><strong>Proof requirement:</strong> {esc(row["proof_requirement"]) or "Unknown"}</p><p>{links}</p><a class="btn secondary" href="/draft?id={row["id"]}">Prepare inquiry draft</a></div>'
                    body += f'<div class="panel"><h2>Track this case</h2><form method="post" action="/update-case">{form_token(self.token)}<input type="hidden" name="id" value="{row["id"]}"><label>Status</label><select name="status">'
                    body += ''.join(f'<option value="{esc(x)}" {"selected" if x==row["status"] else ""}>{esc(x.replace("_", " "))}</option>' for x in store.CASE_STATUSES)
                    body += f'</select><label>Follow-up date (optional)</label><input type="date" name="follow_up_on" value="{esc(row["follow_up_on"])}"><label>Notes</label><textarea name="notes" maxlength="5000">{esc(row["notes"])}</textarea><p><button>Save case</button></p></form></div>'
                    timeline = store.activity(con, row['id'])
                    body += '<div class="panel"><h2>Activity</h2>' + ''.join(f'<p><small>{esc(a["created_at"][:16])} UTC</small> · {esc(a["event"])}</p>' for a in timeline) + '</div>'
                    self.page(row['product_name'], body)
                elif path == '/draft':
                    row = store.get_case(con, int(self.q('id','0')))
                    if not row: return self.fail('Unknown case',404)
                    subject, body = draft_text(row)
                    draft = 'Subject: ' + subject + '\n\n' + body
                    mailto = ('mailto:' + quote(row['contact_email']) + '?subject=' + quote(subject) + '&body=' + quote(body)) if row['contact_email'] else ''
                    page = f'<h1>Inquiry draft</h1><p class="muted">Prepared from the real information recorded in your case. Check accuracy and the manufacturer submission requirements before contacting anyone.</p>'
                    page += f'<div class="panel"><label>Editable copy of the draft</label><textarea style="min-height:300px" id="draft" readonly>{esc(draft)}</textarea><div class="toolbar"><button type="button" onclick="navigator.clipboard.writeText(document.getElementById(\'draft\').value).then(()=>alert(\'Copied\'))">Copy message</button>'
                    if mailto: page += f'<a class="btn secondary" href="{esc(mailto)}">Open email app</a>'
                    if safe_url(row['contact_url']): page += f'<a class="btn secondary" href="{esc(safe_url(row["contact_url"]))}" target="_blank" rel="noopener noreferrer">Open contact form</a>'
                    page += f'<a class="btn secondary" href="/case?id={row["id"]}">Back to case</a></div></div>'
                    # Allow only the small inline clipboard helper on this specific page.
                    self.page('Inquiry draft', page)
                elif path == '/help':
                    self.page('Help', '<h1>How to use WarrantyFlow</h1><div class="panel"><h2>1. Add a real product</h2><p>Choose a manufacturer, describe the item and defect, and save it locally.</p><h2>2. Check the current policy</h2><p>Visit the manufacturer policy link. Imported policy research is marked as needing recheck.</p><h2>3. Prepare an inquiry</h2><p>Use the draft generator and contact link. No warranty messages are sent from the dashboard.</p><h2>4. Track the result</h2><p>Record status, notes and a follow-up date for each case.</p><h2>Data and privacy</h2><p>All case data is stored in a private SQLite file in your home directory, not the GitHub project folder. Run <code>python3 app.py export PATH.csv</code> for a backup. You can quit the server with Ctrl+C.</p></div>')
                else:
                    self.fail('Page not found', 404)
        except (ValueError, TypeError) as exc:
            self.fail(str(exc))

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > 1024 * 1024:
                return self.fail('Invalid form length')
            origin = self.headers.get('Origin', '')
            if origin and origin != 'http://' + self.headers.get('Host', ''):
                return self.fail('Origin mismatch', 403)
            data = parse_qs(self.rfile.read(length).decode('utf-8'), keep_blank_values=True)
            def field(name, default=''):
                return data.get(name, [default])[0]
            if not secrets.compare_digest(field('token'), self.token):
                return self.fail('Invalid form token. Refresh the page.',403)
            path = urlsplit(self.path).path
            with store.database(self.db_path) as con:
                if path == '/add-manufacturer':
                    name = field('name').strip()[:150]
                    if not name: raise ValueError('Manufacturer name required')
                    policy = field('policy_url').strip()
                    contact = field('contact_url').strip()
                    if (policy and not safe_url(policy)) or (contact and not safe_url(contact)):
                        raise ValueError('URLs must start with http:// or https://')
                    store.add_manufacturer(con,name,category=field('category')[:150],policy_url=policy,contact_url=contact)
                    mid = con.execute('SELECT id FROM manufacturers WHERE name=? COLLATE NOCASE',(name,)).fetchone()[0]
                    return self.redirect('/manufacturer?id=' + str(mid))
                if path == '/add-case':
                    mid = int(field('manufacturer_id'))
                    case_id = store.create_case(con, mid, field('product_name')[:180], field('issue')[:2000],
                              field('purchase_info')[:500], field('proof_available') == '1', field('notes')[:3000])
                    return self.redirect('/case?id=' + str(case_id))
                elif path == '/update-case':
                    case_id = int(field('id'))
                    store.edit_case(con,case_id,field('status'),field('notes')[:5000],field('follow_up_on'))
                    return self.redirect('/case?id=' + str(case_id))
                elif path == '/update-manufacturer':
                    mid = int(field('id'))
                    m = store.get_manufacturer(con, mid)
                    if not m: raise ValueError('Unknown manufacturer')
                    status = field('research_status')
                    if status not in store.RESEARCH_STATES: raise ValueError('Invalid research status')
                    email = field('contact_email').strip()
                    if email and (email.count('@') != 1 or any(c.isspace() for c in email) or len(email)>254):
                        raise ValueError('Enter a valid contact email')
                    link = field('contact_url').strip()
                    if link and not safe_url(link): raise ValueError('Contact URL must be http(s)')
                    con.execute('UPDATE manufacturers SET research_status=?, contact_email=?,contact_url=?,verified_at=? WHERE id=?',
                          (status,email,link,date.today().isoformat() if status=='checked' else '',mid))
                    return self.redirect('/manufacturer?id=' + str(mid))
            return self.fail('Unknown action',404)
        except (ValueError, TypeError) as exc:
            self.fail(str(exc))


def launch(db_path=store.DEFAULT_PATH, port=8765, open_browser=True):
    token = secrets.token_urlsafe(32)
    class LocalHandler(Handler):
        pass
    LocalHandler.db_path = db_path
    LocalHandler.token = token
    with ThreadingHTTPServer(('127.0.0.1', port), LocalHandler) as server:
        url = 'http://127.0.0.1:' + str(server.server_address[1])
        print('WarrantyFlow dashboard: ' + url, flush=True)
        print('Press Ctrl+C to stop. Cases are saved privately.', flush=True)
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print('\nDashboard stopped.')
