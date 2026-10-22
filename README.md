# WarrantyFlow

A lightweight Python CLI for researching warranty programs, preparing factual policy inquiries, and tracking outreach through a CSV database.

**Portfolio demo:** Works without API keys, paid services, or external Python packages. No email is sent unless you explicitly run the `send` command with configured credentials and eligible records.

## Features

- CSV-based research database
- One-command setup and reporting
- Personalized policy inquiry templates
- Preview mode and duplicate-recipient prevention
- Gmail SMTP sending for factual inquiries
- Sent timestamps and persistent delivery status
- Unit tests, sample records, and no third-party dependencies

## Quick start

Requires Python 3.9+.

```bash
python3 app.py init
python3 app.py list
python3 app.py report
python3 app.py preview
python3 -m unittest discover -s tests -v
```

`init` creates `data/inquiries.csv` if it does not already exist. Edit this CSV to add company contacts and set `Status` to `ready` only for accurate policy questions. The initial examples have blank contact addresses and `research` status.

## CSV schema

| Column | Meaning |
|---|---|
| Company | Manufacturer or brand |
| Product | Product category |
| Contact Email | Verified support email |
| Policy URL | Official warranty information |
| Question | Optional specific policy question |
| Status | `research`, `ready`, or `sent` |
| Sent At | UTC timestamp after SMTP accepts the message |

## Optional email sending

Only for accurate warranty **policy inquiries**, not unverified claims about product ownership or defects. Use verified business contact addresses and respect company contact preferences.

Set Gmail credentials in your shell (never commit passwords):

```bash
export GMAIL_ADDRESS='you@gmail.com'
export GMAIL_APP_PASSWORD='your-app-password'
python3 app.py preview
python3 app.py send --limit 5
```

`send` does not ask for per-message approval. It sends only rows marked `ready` with valid recipient addresses, skips duplicate addresses, and updates each successful row to `sent`. SMTP acceptance does not guarantee final inbox delivery. The sender stops on an error rather than silently retrying an uncertain delivery.

**Do not use example or invented defect descriptions as genuine warranty claims.** The application deliberately drafts general policy questions rather than making personal ownership or defect assertions.

## Importing research

You can add researched manufacturers by editing `data/inquiries.csv`. Keep private customer information, real claims, Gmail credentials, and live sending databases out of GitHub. The repository ignores `data/*.csv` by default.

## Structure

```text
app.py
replacement_project/cli.py
tests/test_cli.py
data/example.csv
.env.example
.gitignore
README.md
LICENSE
```

## License

MIT
