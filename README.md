# CredVault – ELEVATE SDE Task 3

Backend-only Certificate Issuing & Verification Platform built from the supplied 2-page SRS.

## Stack
Python 3.10+, Flask, SQLite, Flask-CORS. No frontend pages are included.

## Setup (Windows PowerShell)
```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
# If activation is blocked:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```
API base URL: `http://127.0.0.1:5000`. SQLite database `credvault.db` is created automatically.

## Demo admin credentials
Username `admin`; password `admin123`. Change these in `.env` before sharing/deploying.
Login returns an in-memory Bearer token; server restart invalidates tokens. This is a learning/demo implementation, not production authentication.

## Endpoints (all 9 SRS endpoints)
| # | Method | Endpoint | Access |
|---|---|---|---|
| 1 | POST | `/api/applications` | Public |
| 2 | GET | `/api/applications/track/<applicationId>` | Public |
| 3 | GET | `/api/certificates/verify/<certificateId>` | Public |
| 4 | POST | `/api/admin/login` | Public |
| 5 | GET | `/api/admin/applications` | Admin |
| 6 | PATCH | `/api/admin/applications/<applicationId>/approve` | Admin |
| 7 | PATCH | `/api/admin/applications/<applicationId>/reject` | Admin |
| 8 | GET | `/api/admin/certificates` | Admin |
| 9 | GET | `/api/admin/certificates/<certificateId>/revoke` | Admin |

The SRS explicitly specifies GET for certificate revocation, so this implementation follows it. Production APIs should normally use PATCH/POST for state changes.

## Request examples

### Create application
`POST /api/applications`
```json
{"name":"Priya Sharma","phone":"9123456780","gender":"Female","city":"Bengaluru","state":"Karnataka"}
```
Response: `201` with `applicationId` and `Pending` status.

### Admin login
`POST /api/admin/login`
```json
{"username":"admin","password":"admin123"}
```
Send returned token on protected endpoints as header:
`Authorization: Bearer YOUR_TOKEN`

Approve: `PATCH /api/admin/applications/<id>/approve` — generates a certificate ID.
Reject: `PATCH /api/admin/applications/<id>/reject` — optional body `{"reason":"Incomplete details"}`.
Revoke: `GET /api/admin/certificates/<certificateId>/revoke`.

## Database
- applications: applicationId, name, phone, gender, city, state, status, submittedAt
- certificates: certificateId, applicationId, issuedOn, status
- admins: username, password (hashed)

Revoking a certificate updates only the certificate status; the application remains unchanged. Required fields and phone format are validated. The Task 3 SRS says no screenshots are required.
