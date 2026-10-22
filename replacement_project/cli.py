"""WarrantyFlow browser and utility commands."""
import argparse
import os
import smtplib
from pathlib import Path
from . import store
from .webapp import launch

SEED = Path(__file__).resolve().parent.parent / 'data' / 'manufacturers.csv'


def seed_if_empty(con):
    if con.execute('SELECT COUNT(*) FROM manufacturers').fetchone()[0] == 0 and SEED.exists():
        return store.import_research(con, SEED)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description='WarrantyFlow: a private, local warranty dashboard')
    parser.add_argument('--db', type=Path, default=store.DEFAULT_PATH,
                        help='SQLite database location (default: ~/.warrantyflow/warrantyflow.sqlite3)')
    subs = parser.add_subparsers(dest='command')
    serve = subs.add_parser('serve', help='Open dashboard (default)')
    serve.add_argument('--port', type=int, default=8765)
    serve.add_argument('--no-browser', action='store_true')
    imp = subs.add_parser('import', help='Import manufacturers from an existing research CSV')
    imp.add_argument('csv_file', type=Path)
    subs.add_parser('report', help='Show local database statistics')
    outgoing = subs.add_parser('policy-send', help='Automatically send only factual policy questions to checked contacts')
    outgoing.add_argument('--limit', type=int, default=3, help='Maximum recipients per run (1 to 20)')
    outgoing.add_argument('--delay', type=int, default=30, help='Seconds between messages (default 30)')
    export = subs.add_parser('export', help='Export your cases to a private CSV backup')
    export.add_argument('csv_file', type=Path)
    args = parser.parse_args(argv)
    with store.database(args.db) as con:
        seeded = seed_if_empty(con)
        if seeded:
            print('Added', seeded, 'manufacturer reference records (policies marked for rechecking).')
        if args.command == 'import':
            imported = store.import_research(con,args.csv_file)
            print('Imported', imported, 'manufacturer records. Private case data unchanged.')
            return
        if args.command == 'policy-send':
            from .mailer import prepared, send_policy_inquiries
            ready = prepared(con)
            print('Verified contacts eligible for an initial policy inquiry:', len(ready))
            if not ready:
                print('Nothing sent. Check current policies and add official contact emails first.')
                return
            address = os.environ.get('GMAIL_ADDRESS','').strip()
            password = os.environ.get('GMAIL_APP_PASSWORD','').replace(' ','')
            try:
                count = send_policy_inquiries(con,address,password,limit=args.limit,delay=args.delay)
            except (ValueError,OSError,smtplib.SMTPException) as error:
                raise SystemExit('Sending stopped: '+str(error))
            print('Completed policy inquiries:',count)
            return
        if args.command == 'report':
            for label, value in store.stats(con).items():
                print(label.replace('_',' ').title() + ':', value)
            print('Private database:', args.db)
            return
        if args.command == 'export':
            if args.csv_file.resolve().is_relative_to(Path(__file__).resolve().parent.parent):
                raise SystemExit('Export outside the project folder to avoid publishing private case details.')
            count = store.export_cases(con,args.csv_file)
            print('Exported', count, 'private cases to',args.csv_file)
            return
    if args.command in (None,'serve'):
        launch(args.db, port=getattr(args, 'port',8765), open_browser=not getattr(args,'no_browser',False))


if __name__ == '__main__':
    main()
