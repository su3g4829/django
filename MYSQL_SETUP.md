# MySQL Setup

## Current expectation

- MySQL is the active persistence layer for this project.
- Django ORM is the only supported runtime data path.
- Do not restore or depend on `data/*.json` for normal application behavior.

## Local workflow

1. Create a local MySQL database.
2. Put the connection settings in `store/.env`.
3. Run `..\Scripts\python.exe manage.py migrate`.
4. Verify Django can query the database.

## Safety

- Do not commit database dumps.
- Do not commit local passwords, certificates, or exported customer data.

## Full sync guide

- For full Windows + PowerShell steps covering:
  - local MySQL upload to Aiven
  - Aiven dump download
  - restore back into local MySQL
  - SSL, encoding, and PowerShell redirection errors
- See [AIVEN_MYSQL_SYNC.md](AIVEN_MYSQL_SYNC.md)
