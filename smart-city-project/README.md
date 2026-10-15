# SmartCity Portal — Flask + SQLite

A functional starter backend for the supplied SmartCity frontend.

## Run locally (Windows)

1. Install Python 3.10 or newer.
2. Open a terminal in this folder.
3. Create and activate a virtual environment:
   ```powershell
   py -m venv .venv
   .venv\\Scripts\\activate
   ```
4. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
5. Start the server:
   ```powershell
   python app.py
   ```
6. Open http://127.0.0.1:5000

## Features

- Citizen registration, password hashing, login and session logout
- SQLite database automatically initialized in `instance/smartcity.sqlite3`
- Issue reports, status tracking and +20 points per report
- Suggestions, optional anonymous flag and +10 points per suggestion
- Admin announcements that appear in citizen pages, including ward targeting
- Demo payment records and admin payment view
- Admin citizen search and issue status management
- `/health` health-check endpoint

## Demo admin login

- Email: `admin@smartcity.gov`
- Password: `Admin@12345`

Set `ADMIN_PASSWORD` before the first run to use a different initial admin password. Set `SECRET_KEY` to a long random value before deployment. The default values are for local development only.

## Important production notes

- Payment records are **not real payments**. No money is charged. Integrate and verify a payment provider such as Safaricom M-Pesa Daraja before using payments for real transactions.
- The Ask AI visual from the original prototype is not connected to an AI service in this version.
- Add CSRF protection, rate limiting, HTTPS, secure cookie settings, admin password management, and stronger validation before public deployment.
- SQLite is suitable for a local MVP; consider managed PostgreSQL for production hosting.
