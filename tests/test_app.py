import csv
import io
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from replacement_project import store
from replacement_project.cli import SEED, seed_if_empty
from replacement_project.webapp import Handler, draft_text, safe_url


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'cases.sqlite3'

    def test_seed_has_50_real_manufacturer_names_no_demo_cases(self):
        with store.database(self.path) as con:
            self.assertEqual(seed_if_empty(con), 50)
            self.assertEqual(store.stats(con)['manufacturers'], 50)
            self.assertEqual(store.stats(con)['cases'], 0)
            self.assertEqual(store.stats(con)['needs_recheck'], 50)
            self.assertEqual(seed_if_empty(con), 0)

    def test_manufacturers_do_not_duplicate_during_import(self):
        with store.database(self.path) as con:
            store.import_research(con, SEED)
            store.import_research(con, SEED)
            self.assertEqual(store.stats(con)['manufacturers'], 50)

    def test_no_private_claim_fields_imported(self):
        with store.database(self.path) as con:
            store.import_research(con, SEED)
            self.assertEqual(len(store.cases(con)), 0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM activity').fetchone()[0], 0)

    def test_create_case_status_followup_and_timeline(self):
        with store.database(self.path) as con:
            store.add_manufacturer(con, 'Sample Co')
            company = store.manufacturers(con)[0]['id']
            case_id = store.create_case(con, company, 'Coffee brewer', 'Button does not work', proof_available=True)
            self.assertEqual(store.get_case(con, case_id)['status'], 'draft')
            store.edit_case(con, case_id, 'awaiting_reply', 'Emailed support', '2026-12-12')
            row = store.get_case(con, case_id)
            self.assertEqual(row['status'], 'awaiting_reply')
            self.assertEqual(row['follow_up_on'], '2026-12-12')
            self.assertGreaterEqual(len(store.activity(con, case_id)), 2)

    def test_invalid_case_data_rejected(self):
        with store.database(self.path) as con:
            with self.assertRaises(ValueError):
                store.create_case(con, None, '', 'Broken')
            with self.assertRaises(ValueError):
                store.create_case(con, 999999, 'Item', 'Broken')
            with self.assertRaises(ValueError):
                store.edit_case(con, 99999, 'resolved', '')

    def test_invalid_follow_up_date_rejected(self):
        with store.database(self.path) as con:
            i = store.create_case(con, None, 'Item', 'Defect')
            with self.assertRaises(ValueError):
                store.edit_case(con, i, 'ready', '', 'today')

    def test_case_export(self):
        with store.database(self.path) as con:
            store.create_case(con, None, 'Blender', 'Leaking')
            export = Path(self.temp.name) / 'cases.csv'
            self.assertEqual(store.export_cases(con, export), 1)
        with export.open(newline='') as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(rows[0]['product_name'], 'Blender')

    def test_no_unsafe_policy_links(self):
        self.assertEqual(safe_url('javascript:alert(1)'), '')
        self.assertEqual(safe_url('https://example.com/warranty'), 'https://example.com/warranty')

    def test_draft_only_uses_actual_case_details(self):
        with store.database(self.path) as con:
            store.add_manufacturer(con,'Test Brand')
            mid = store.manufacturers(con)[0]['id']
            cid = store.create_case(con,mid,'Jacket','The zipper is broken')
            subject, body = draft_text(store.get_case(con,cid))
        self.assertIn('The zipper is broken',body)
        self.assertIn('Jacket',subject)
        self.assertNotIn('SuperBreak',body)


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.temp.name) / 'web.sqlite3'
        with store.database(cls.path) as con:
            store.add_manufacturer(con, 'Test & Sons', policy_url='https://example.com')
        class TestHandler(Handler):
            pass
        TestHandler.db_path = cls.path
        TestHandler.token = 'test-secret-token'
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), TestHandler)
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_address[1])
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.temp.cleanup()

    def get(self, route):
        with urllib.request.urlopen(self.url+route,timeout=3) as r:
            return r.status, r.read().decode('utf-8')

    def post(self, route, values):
        data = urllib.parse.urlencode(values).encode('utf-8')
        req = urllib.request.Request(self.url+route, data=data, method='POST')
        try:
            with urllib.request.urlopen(req,timeout=3) as r:
                return r.status, r.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode('utf-8')

    def test_dashboard_loads(self):
        status, html = self.get('/')
        self.assertEqual(status, 200)
        self.assertIn('Warranty organizer',html)

    def test_manufacturer_name_escaped(self):
        _, html = self.get('/manufacturers')
        self.assertIn('Test &amp; Sons', html)

    def test_bad_form_token_rejected(self):
        status, text = self.post('/add-case',{'token':'wrong','manufacturer_id':'1','product_name':'X','issue':'Y'})
        self.assertEqual(status,403)
        self.assertIn('Invalid form token',text)

    def test_add_case_via_dashboard(self):
        status, _ = self.post('/add-case',{'token':'test-secret-token','manufacturer_id':'1','product_name':'Water bottle','issue':'Cracked handle'})
        self.assertEqual(status,200)
        _, html = self.get('/cases')
        self.assertIn('Water bottle',html)
        self.assertIn('Cracked handle',html)

    def test_bad_status_rejected(self):
        with store.database(self.path) as con:
            cid = store.cases(con)[0]['id']
        status, _ = self.post('/update-case', {'token':'test-secret-token','id':str(cid),'status':'bad','notes':''})
        self.assertEqual(status,400)


if __name__=='__main__':
    unittest.main()

class MailerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'mailer.sqlite3'

    def _setup(self):
        with store.database(self.path) as con:
            store.add_manufacturer(con,'Brand Alpha',category='Backpacks',contact_email='help@example.com',research_status='checked')
            store.add_manufacturer(con,'Brand Beta',category='Water Bottles',contact_email='HELP@example.com',research_status='checked')
            store.add_manufacturer(con,'Brand Gamma',category='Socks',contact_email='info@example.com',research_status='needs_recheck')
            con.commit()

    def test_persistent_recipient_deduplication(self):
        from replacement_project.mailer import send_policy_inquiries, prepared
        self._setup()
        sent_messages = []
        class MockSMTP:
            def __init__(self,*args,**kwargs): pass
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def login(self,*args): pass
            def send_message(self,msg): sent_messages.append(msg)
        with store.database(self.path) as con:
            self.assertEqual(len(prepared(con)),1)
            self.assertEqual(send_policy_inquiries(con,'sender@gmail.com','fake',smtp_factory=MockSMTP,delay=0),1)
            self.assertEqual(len(prepared(con)),0)
            self.assertEqual(send_policy_inquiries(con,'sender@gmail.com','fake',smtp_factory=MockSMTP,delay=0),0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM policy_outreach').fetchone()[0],1)
            self.assertEqual(store.stats(con)['policy_inquiries_sent'],1)
        self.assertEqual(len(sent_messages),1)
        self.assertNotIn('defect',sent_messages[0].get_content().lower())

    def test_smtp_error_marks_recipient_uncertain_and_never_retries(self):
        import smtplib
        from replacement_project.mailer import send_policy_inquiries, prepared
        self._setup()
        class BrokenSMTP:
            def __init__(self,*args,**kwargs):pass
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def login(self,*args):pass
            def send_message(self,msg):raise smtplib.SMTPServerDisconnected('connection dropped')
        with store.database(self.path) as con:
            with self.assertRaises(smtplib.SMTPServerDisconnected):
                send_policy_inquiries(con,'sender@gmail.com','fake',smtp_factory=BrokenSMTP,delay=0)
            self.assertEqual(len(prepared(con)),0)
            self.assertEqual(con.execute('SELECT state FROM policy_outreach').fetchone()[0],'uncertain')

    def test_unchecked_contacts_cannot_send(self):
        from replacement_project.mailer import prepared
        with store.database(self.path) as con:
            store.add_manufacturer(con,'Not Checked',contact_email='support@example.com',research_status='needs_recheck')
            self.assertEqual(len(prepared(con)),0)

class AdditionalUsabilityTests(unittest.TestCase):
    def test_due_followups_excludes_resolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            with store.database(Path(tmp) / 'sample.sqlite3') as con:
                due_id = store.create_case(con,None,'To follow up','Broken')
                resolved_id = store.create_case(con,None,'Resolved','Broken')
                store.edit_case(con,due_id,'awaiting_reply','', '2020-01-01')
                store.edit_case(con,resolved_id,'resolved','', '2020-01-01')
                self.assertEqual(len(store.due_followups(con)),1)
                self.assertEqual(store.due_followups(con)[0]['id'],due_id)
