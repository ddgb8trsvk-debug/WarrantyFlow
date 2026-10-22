# WarrantyFlow 2.0

**A private, local-first warranty organizer built with Python.** Track your products, look up manufacturer policies, write accurate warranty inquiries, and manage follow-up dates in your browser.

Runs entirely on your computer with **Python 3.9+ and no third-party packages**. No accounts, subscriptions, or API keys required.

## Quick start

```bash
python3 app.py
```

Open `http://127.0.0.1:8765` if your browser does not open automatically. Stop the server with Ctrl+C.

First launch imports **50 manufacturer reference records**. These records are research leads, not live verification. All entries are marked **needs recheck**. The program does **not** import fictional product claims from past demonstration files.

## Features

- Local browser dashboard with totals and recent cases
- Searchable 50-manufacturer starter reference database, plus ability to add additional brands
- Product issue tracking, evidence checkbox, notes, statuses, due follow-ups, and activity timeline
- Manufacturer policy/contact links and editable contact details
- Factual inquiry drafts generated from case information you enter
- Activity timeline and private CSV export
- SQLite storage outside the project folder, at `~/.warrantyflow/warrantyflow.sqlite3`
- Optional unattended Gmail policy-question sender, restricted to checked manufacturer contacts, with persistent duplicate protection
- Zero external Python dependencies and automated unit/integration tests

## Commands

```bash
python3 app.py                 # start the dashboard
python3 app.py report          # summary
python3 app.py import PATH.csv # import or update manufacturer research
python3 app.py export ~/Desktop/my-warranty-cases.csv
python3 -m unittest discover -s tests -v
python3 app.py policy-send --limit 3  # optional, after configuring Gmail and checked contacts
```

The browser binds to **127.0.0.1 only**. It is not a hosted website and does not fetch policies in the background. The draft page opens the manufacturer's contact form or your email app, when contact details are present. This makes the core application usable without granting email account access.

### Optional automated policy inquiries

This is an opt-in **command**, not a background service. After reviewing each current manufacturer policy, mark that company's research status `checked` in the dashboard and record its verified support email address. The CLI can then send **general, factual warranty-policy questions** without requiring approval for every message:

```bash
export GMAIL_ADDRESS='you@gmail.com'
export GMAIL_APP_PASSWORD='your-google-app-password'
python3 app.py policy-send --limit 3
```

The sender does not mention product ownership or defects, even if your private case database contains them. It skips previously attempted recipients across runs (including uncertain deliveries), caps batches at 20, and pauses between messages. Gmail credentials are read from environment variables and never written to the project database. Initial reference entries have no verified recipient emails and are **not send-ready**.

The sender records SMTP acceptance, not guaranteed delivery. No mailbox monitoring is implemented.

## Accurate expectations

Warranty eligibility depends on real ownership, product condition, and the manufacturer's current policy. This application does not guarantee a replacement, decide eligibility automatically, or submit unsupported claims.

The included reference CSV is intended as a starting point for research. Its links and policy summaries may change. Always consult official documentation before using a claim.

## Privacy

**Do not commit personal case databases or credentials to GitHub.** The shipped code contains no real email passwords, personal contact details, or example defect claims. The SQLite database is deliberately stored in your home directory, outside Git. Exports contain private case information; keep them private.

## Architecture

- `app.py`: minimal entry point
- `replacement_project/cli.py`: command-line interface and data seeding
- `replacement_project/store.py`: parameterized SQLite data access and research import
- `replacement_project/webapp.py`: localhost-only browser UI with form token verification
- `data/manufacturers.csv`: public sample research leads (50 companies)
- `tests/`: automated tests

## Limitations and future development

Automated official policy rechecking, OAuth Gmail integration, robust contact discovery, document attachments, and inbox reply matching are **not yet implemented**. This is a usable local portfolio project, not a hosted SaaS or an autonomous warranty-claim service.

## License

MIT

## Upgrading an existing WarrantyFlow v1 GitHub checkout

If you already have the original project in `~/Projects/WarrantyFlow`, the downloadable ZIP includes `upgrade_my_repo.sh` to update the source safely. It backs up existing source code outside Git, runs tests, commits only specific project files, and never stages private case data. To upgrade locally only:

```bash
sh upgrade_my_repo.sh
```

To also publish to the configured GitHub repository in one operation:

```bash
sh upgrade_my_repo.sh --publish
```

The repository URL is restricted in this convenience script to the original project owner, and the script itself is not copied into the published repository. The update never force-pushes. The script needs an existing clean `main` checkout with Git authentication already configured.
