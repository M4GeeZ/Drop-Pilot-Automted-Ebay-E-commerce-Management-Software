from getpass import getpass
from auth import make_hash
p=getpass('Enter NEW DropPilot password (not displayed): ')
if len(p)<12:raise SystemExit('Use at least 12 characters.')
if p!=getpass('Confirm password: '):raise SystemExit('Passwords do not match.')
print('\nCopy the following value into DROPPILOT_PASSWORD_HASH in Vercel:\n'+make_hash(p))
