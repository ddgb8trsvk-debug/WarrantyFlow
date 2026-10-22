import tempfile
import unittest
from pathlib import Path
from replacement_project.cli import FIELDS, draft, eligible, init, read_db, save_db

class WarrantyFlowTests(unittest.TestCase):
    def test_init_preserves_existing_data(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'inquiries.csv'
            init(path)
            self.assertEqual(len(read_db(path)), 5)
            init(path)
            self.assertEqual(len(read_db(path)), 5)

    def test_duplicate_and_sent_protection(self):
        rows = [dict.fromkeys(FIELDS, '') for _ in range(3)]
        for row in rows:
            row.update({'Company': 'Example', 'Product': 'Bags', 'Contact Email': 'help@example.com', 'Status': 'ready'})
        rows[2]['Status'] = 'sent'
        self.assertEqual(len(list(eligible(rows))), 1)

    def test_policy_inquiry_does_not_claim_defect(self):
        subject, body = draft({'Company': 'Example', 'Product': 'Bags', 'Question': ''})
        self.assertIn('eligibility requirements', body)
        self.assertNotIn('my defective', body)

if __name__ == '__main__':
    unittest.main()
