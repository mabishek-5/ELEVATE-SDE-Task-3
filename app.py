import os, sqlite3, secrets
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, jsonify, request, g
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()
app=Flask(__name__)
CORS(app)
DB=os.getenv("DATABASE_PATH","credvault.db")
ADMIN_USER=os.getenv("ADMIN_USERNAME","admin")
ADMIN_PASS=os.getenv("ADMIN_PASSWORD","admin123")
TOKENS=set()

def db():
    if "db" not in g:
        g.db=sqlite3.connect(DB)
        g.db.row_factory=sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def close_db(_):
    conn=g.pop("db",None)
    if conn: conn.close()

def init_db():
    c=sqlite3.connect(DB)
    c.executescript("""
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS applications(
      applicationId TEXT PRIMARY KEY, name TEXT NOT NULL, phone TEXT NOT NULL,
      gender TEXT NOT NULL, city TEXT NOT NULL, state TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending','Approved','Rejected')),
      submittedAt TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS certificates(
      certificateId TEXT PRIMARY KEY, applicationId TEXT NOT NULL UNIQUE,
      issuedOn TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Valid' CHECK(status IN ('Valid','Revoked')),
      FOREIGN KEY(applicationId) REFERENCES applications(applicationId));
    CREATE TABLE IF NOT EXISTS admins(username TEXT PRIMARY KEY,password TEXT NOT NULL);
    """)
    if not c.execute("SELECT 1 FROM admins WHERE username=?",(ADMIN_USER,)).fetchone():
        c.execute("INSERT INTO admins VALUES(?,?)",(ADMIN_USER,generate_password_hash(ADMIN_PASS)))
    c.commit(); c.close()

def ident(prefix):
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"
def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def err(msg,code): return jsonify(success=False,message=msg),code
def protected(fn):
    @wraps(fn)
    def inner(*a,**kw):
        token=request.headers.get("Authorization","").removeprefix("Bearer ").strip()
        if token not in TOKENS: return err("Admin authentication required.",401)
        return fn(*a,**kw)
    return inner

@app.get("/")
def home(): return jsonify(name="CredVault API",status="running",version="1.0.0")
@app.get("/api/health")
def health(): return jsonify(success=True,status="healthy")

@app.post("/api/applications")
def create_application():
    d=request.get_json(silent=True) or {}
    fields=["name","phone","gender","city","state"]
    missing=[x for x in fields if not str(d.get(x,"")).strip()]
    if missing: return err("Missing required fields: "+", ".join(missing),400)
    vals=[str(d[x]).strip() for x in fields]
    if not 2<=len(vals[0])<=100: return err("Name must be 2 to 100 characters.",400)
    if not vals[1].isdigit() or not 7<=len(vals[1])<=15: return err("Phone must contain 7 to 15 digits.",400)
    aid=ident("APP")
    db().execute("INSERT INTO applications VALUES(?,?,?,?,?,?,?,?)",
       (aid,*vals,"Pending",now()))
    db().commit()
    return jsonify(success=True,message="Certificate application submitted successfully.",
                   applicationId=aid,status="Pending"),201

@app.get("/api/applications/track/<application_id>")
def track(application_id):
    r=db().execute("SELECT applicationId,name,status,submittedAt FROM applications WHERE applicationId=?",(application_id,)).fetchone()
    return (jsonify(dict(r)),200) if r else err("Application not found.",404)

@app.get("/api/certificates/verify/<certificate_id>")
def verify(certificate_id):
    r=db().execute("""SELECT c.certificateId,a.name,a.phone,c.issuedOn,c.status
      FROM certificates c JOIN applications a ON a.applicationId=c.applicationId
      WHERE c.certificateId=?""",(certificate_id,)).fetchone()
    return (jsonify(dict(r)),200) if r else err("Certificate not found.",404)

@app.post("/api/admin/login")
def login():
    d=request.get_json(silent=True) or {}
    u=str(d.get("username","")).strip(); p=str(d.get("password",""))
    if not u or not p: return err("Username and password are required.",400)
    r=db().execute("SELECT * FROM admins WHERE username=?",(u,)).fetchone()
    if not r or not check_password_hash(r["password"],p): return err("Invalid username or password.",401)
    t=secrets.token_urlsafe(32); TOKENS.add(t)
    return jsonify(success=True,message="Admin login successful.",token=t,admin={"username":u}),200

@app.get("/api/admin/applications")
@protected
def list_apps():
    return jsonify([dict(r) for r in db().execute("SELECT * FROM applications ORDER BY submittedAt DESC")]),200

@app.patch("/api/admin/applications/<application_id>/approve")
@protected
def approve(application_id):
    c=db(); a=c.execute("SELECT * FROM applications WHERE applicationId=?",(application_id,)).fetchone()
    if not a: return err("Application not found.",404)
    if a["status"]=="Rejected": return err("A rejected application cannot be approved.",409)
    old=c.execute("SELECT certificateId FROM certificates WHERE applicationId=?",(application_id,)).fetchone()
    if old: return jsonify(success=True,message="Application already approved.",applicationId=application_id,certificateId=old["certificateId"])
    cid=ident("CERT")
    c.execute("UPDATE applications SET status='Approved' WHERE applicationId=?",(application_id,))
    c.execute("INSERT INTO certificates VALUES(?,?,?,'Valid')",(cid,application_id,datetime.now(timezone.utc).date().isoformat()))
    c.commit()
    return jsonify(success=True,message="Application approved and certificate issued.",applicationId=application_id,certificateId=cid),200

@app.patch("/api/admin/applications/<application_id>/reject")
@protected
def reject(application_id):
    d=request.get_json(silent=True) or {}
    c=db(); a=c.execute("SELECT status FROM applications WHERE applicationId=?",(application_id,)).fetchone()
    if not a: return err("Application not found.",404)
    if a["status"]=="Approved": return err("An approved application cannot be rejected.",409)
    c.execute("UPDATE applications SET status='Rejected' WHERE applicationId=?",(application_id,)); c.commit()
    out={"success":True,"message":"Application rejected.","applicationId":application_id}
    if d.get("reason"): out["reason"]=str(d["reason"])
    return jsonify(out),200

@app.get("/api/admin/certificates")
@protected
def list_certs():
    rows=db().execute("""SELECT c.certificateId,c.applicationId,a.name,a.phone,a.city,a.state,c.issuedOn,c.status
      FROM certificates c JOIN applications a ON a.applicationId=c.applicationId ORDER BY c.issuedOn DESC""")
    return jsonify([dict(r) for r in rows]),200

# GET is retained because the supplied SRS explicitly specifies GET for revoke.
@app.get("/api/admin/certificates/<certificate_id>/revoke")
@protected
def revoke(certificate_id):
    c=db(); r=c.execute("SELECT status FROM certificates WHERE certificateId=?",(certificate_id,)).fetchone()
    if not r: return err("Certificate not found.",404)
    c.execute("UPDATE certificates SET status='Revoked' WHERE certificateId=?",(certificate_id,))
    c.commit()
    return jsonify(success=True,message="Certificate revoked.",certificateId=certificate_id,status="Revoked"),200

@app.errorhandler(404)
def missing(_): return err("Route not found.",404)
@app.errorhandler(405)
def method_error(_): return err("Method not allowed.",405)

if __name__=="__main__":
    init_db()
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","5000")),debug=os.getenv("FLASK_DEBUG","false").lower()=="true")
