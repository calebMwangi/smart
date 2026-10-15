import os, sqlite3
from functools import wraps
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-before-deploying")
app.config["DATABASE"] = os.environ.get("DATABASE_PATH", os.path.join(app.instance_path, "smartcity.sqlite3"))
os.makedirs(app.instance_path, exist_ok=True)


UPLOAD_FOLDER = './static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    conn = g.pop("db", None)
    if conn is not None: conn.close()

def init_db():
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS citizens (
      id INTEGER PRIMARY KEY AUTOINCREMENT, first_name TEXT NOT NULL, last_name TEXT NOT NULL,
      email TEXT NOT NULL UNIQUE, phone TEXT NOT NULL, national_id TEXT NOT NULL,
      ward TEXT NOT NULL, password_hash TEXT NOT NULL, points INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS issues (
      id INTEGER PRIMARY KEY AUTOINCREMENT, citizen_id INTEGER NOT NULL, title TEXT NOT NULL,
      category TEXT NOT NULL, priority TEXT NOT NULL, location TEXT NOT NULL, description TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'Received', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(citizen_id) REFERENCES citizens(id)
    );
    CREATE TABLE IF NOT EXISTS suggestions (
      id INTEGER PRIMARY KEY AUTOINCREMENT, citizen_id INTEGER, title TEXT NOT NULL, area TEXT NOT NULL,
      idea TEXT NOT NULL, anonymous INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(citizen_id) REFERENCES citizens(id)
    );
    CREATE TABLE IF NOT EXISTS announcements (
      id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, department TEXT NOT NULL,
      kind TEXT NOT NULL, audience TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS payments (
      id INTEGER PRIMARY KEY AUTOINCREMENT, citizen_id INTEGER NOT NULL, bill TEXT NOT NULL,
      amount REAL NOT NULL, method TEXT NOT NULL, phone TEXT NOT NULL, reference TEXT NOT NULL UNIQUE,
      status TEXT NOT NULL DEFAULT 'Pending - demo only', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(citizen_id) REFERENCES citizens(id)
    );
    """)
    # A local demo admin is created only when no admin account exists.
    conn.execute("""CREATE TABLE IF NOT EXISTS admins (
      id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL
    )""")
    if not conn.execute("SELECT 1 FROM admins LIMIT 1").fetchone():
        conn.execute("INSERT INTO admins(email,password_hash) VALUES(?,?)",
                     ("admin@smartcity.gov", generate_password_hash(os.environ.get("ADMIN_PASSWORD", "Admin@12345"))))
    conn.commit(); conn.close()

def citizen_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("citizen_id") is None:
            flash("Please sign in to access the citizen portal.", "error")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("admin_id") is None:
            flash("Please sign in as an administrator.", "error")
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapper

def current_citizen():
    return db().execute("SELECT * FROM citizens WHERE id=?", (session.get("citizen_id"),)).fetchone()

@app.context_processor
def shared_context():
    return {"current_citizen": current_citizen() if session.get("citizen_id") else None,
            "is_admin": bool(session.get("admin_id"))}

@app.route("/")
def login():
    if session.get("citizen_id"): return redirect(url_for("citizen_dashboard"))
    return render_template("login.html")

@app.post("/login")
def do_login():
    email=request.form.get("email","").strip().lower()
    user=db().execute("SELECT * FROM citizens WHERE email=?", (email,)).fetchone()
    if not user or not check_password_hash(user["password_hash"], request.form.get("password","")):
        flash("Invalid email or password.", "error"); return redirect(url_for("login"))
    session.clear(); session["citizen_id"]=user["id"]
    return redirect(url_for("citizen_dashboard"))

@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method=="POST":
        first=request.form.get("first","").strip(); last=request.form.get("last","").strip()
        email=request.form.get("email","").strip().lower(); phone=request.form.get("phone","").strip()
        national_id=request.form.get("national_id","").strip(); ward=request.form.get("ward","").strip()
        password=request.form.get("password","")
        if not all([first,last,email,phone,national_id,ward]) or len(password)<8:
            flash("Complete all fields and use a password of at least 8 characters.", "error")
        else:
            try:
                db().execute("""INSERT INTO citizens(first_name,last_name,email,phone,national_id,ward,password_hash)
                              VALUES(?,?,?,?,?,?,?)""",(first,last,email,phone,national_id,ward,generate_password_hash(password)))
                db().commit(); flash("Account created. You can now sign in.", "success"); return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("An account with that email already exists.", "error")
    return render_template("signup.html")

@app.route("/logout")
def logout():
    session.clear(); flash("You have been signed out.", "success"); return redirect(url_for("login"))

@app.route("/citizen")
@citizen_required
def citizen_dashboard():
    c=current_citizen(); conn=db()
    stats={
      "issues":conn.execute("SELECT COUNT(*) FROM issues WHERE citizen_id=?",(c["id"],)).fetchone()[0],
      "suggestions":conn.execute("SELECT COUNT(*) FROM suggestions WHERE citizen_id=?",(c["id"],)).fetchone()[0],
      "payments":conn.execute("SELECT COUNT(*) FROM payments WHERE citizen_id=?",(c["id"],)).fetchone()[0]}
    issues=conn.execute("SELECT * FROM issues WHERE citizen_id=? ORDER BY id DESC LIMIT 5",(c["id"],)).fetchall()
    announcements=conn.execute("SELECT * FROM announcements WHERE audience='All citizens' OR audience=? ORDER BY id DESC LIMIT 4",(c["ward"],)).fetchall()
    return render_template("citizen_dashboard.html",citizen=c,stats=stats,issues=issues,announcements=announcements)

@app.route("/citizen/announcements")
@citizen_required
def citizen_announcements():
    c=current_citizen()
    items=db().execute("SELECT * FROM announcements WHERE audience='All citizens' OR audience=? ORDER BY id DESC",(c["ward"],)).fetchall()
    return render_template("announcements.html",items=items)

@app.route("/citizen/issues", methods=["GET","POST"])
@citizen_required
def citizen_issues():
    c=current_citizen()
    if request.method=="POST":
        vals=[request.form.get(k,"").strip() for k in ("title","category","priority","location","description")]
        if not all(vals): flash("Please complete every field.", "error")
        else:
            db().execute("INSERT INTO issues(citizen_id,title,category,priority,location,description) VALUES(?,?,?,?,?,?)",(c["id"],*vals))
            db().execute("UPDATE citizens SET points=points+20 WHERE id=?",(c["id"],)); db().commit()
            flash("Issue submitted. You earned 20 citizen points.", "success"); return redirect(url_for("citizen_issues"))
    items=db().execute("SELECT * FROM issues WHERE citizen_id=? ORDER BY id DESC",(c["id"],)).fetchall()
    return render_template("issues.html",items=items,admin_view=False)

def allowed_file(filename):
   return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':

        if 'file' not in request.files:
            return 'No file part'

    file = request.files['file']
    

    if file.filename == '':
        return 'No selected file'
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return f'File uploaded successfully: {filename}'

@app.route("/citizen/suggestions", methods=["GET","POST"])
@citizen_required
def citizen_suggestions():
    c=current_citizen()
    if request.method=="POST":
        title=request.form.get("title","").strip(); area=request.form.get("area","").strip(); idea=request.form.get("idea","").strip()
        anon=1 if request.form.get("anonymous") else 0
        if not all([title,area,idea]): flash("Complete all suggestion fields.", "error")
        else:
            db().execute("INSERT INTO suggestions(citizen_id,title,area,idea,anonymous) VALUES(?,?,?,?,?)",(c["id"],title,area,idea,anon))
            db().execute("UPDATE citizens SET points=points+10 WHERE id=?",(c["id"],)); db().commit()
            flash("Suggestion submitted. You earned 10 citizen points.", "success"); return redirect(url_for("citizen_suggestions"))
    items=db().execute("SELECT * FROM suggestions WHERE citizen_id=? ORDER BY id DESC",(c["id"],)).fetchall()
    return render_template("suggestions.html",items=items)

@app.route("/citizen/payments", methods=["GET","POST"])
@citizen_required
def citizen_payments():
    c=current_citizen()
    if request.method=="POST":
        bill=request.form.get("bill","").strip(); method=request.form.get("method","").strip(); phone=request.form.get("phone","").strip()
        try: amount=float(request.form.get("amount","0"))
        except ValueError: amount=0
        if not bill or not method or not phone or amount<=0: flash("Enter valid payment details.", "error")
        else:
            ref="SC"+datetime.now().strftime("%y%m%d%H%M%S%f")
            db().execute("INSERT INTO payments(citizen_id,bill,amount,method,phone,reference) VALUES(?,?,?,?,?,?)",(c["id"],bill,amount,method,phone,ref))
            db().commit()
            flash("Demo payment record saved. No money was charged; connect a payment provider before real payments.", "success")
            return redirect(url_for("citizen_payments"))
    items=db().execute("SELECT * FROM payments WHERE citizen_id=? ORDER BY id DESC",(c["id"],)).fetchall()
    return render_template("payments.html",items=items)

@app.route("/citizen/waste")
@citizen_required
def citizen_waste():
    return render_template("waste.html")

@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method=="POST":
        email=request.form.get("email","").strip().lower()
        admin=db().execute("SELECT * FROM admins WHERE email=?",(email,)).fetchone()
        if admin and check_password_hash(admin["password_hash"],request.form.get("password","")):
            session.clear(); session["admin_id"]=admin["id"]; return redirect(url_for("admin_dashboard"))
        flash("Invalid administrator credentials.", "error")
    return render_template("admin_login.html")

@app.route("/admin")
@admin_required
def admin_dashboard():
    conn=db()
    stats={"citizens":conn.execute("SELECT COUNT(*) FROM citizens").fetchone()[0],
           "issues":conn.execute("SELECT COUNT(*) FROM issues").fetchone()[0],
           "open_issues":conn.execute("SELECT COUNT(*) FROM issues WHERE status!='Resolved'").fetchone()[0],
           "payments":conn.execute("SELECT COALESCE(SUM(amount),0) FROM payments").fetchone()[0]}
    issues=conn.execute("SELECT i.*,c.first_name,c.last_name FROM issues i JOIN citizens c ON c.id=i.citizen_id ORDER BY i.id DESC LIMIT 6").fetchall()
    return render_template("admin_dashboard.html",stats=stats,issues=issues)

@app.route("/admin/citizens")
@admin_required
def admin_citizens():
    q=request.args.get("q","").strip()
    citizens=db().execute("""SELECT * FROM citizens WHERE first_name LIKE ? OR last_name LIKE ? OR email LIKE ? ORDER BY id DESC""",
                           (f"%{q}%",f"%{q}%",f"%{q}%")).fetchall()
    return render_template("admin_citizens.html",citizens=citizens,q=q)

@app.route("/admin/announcements", methods=["GET","POST"])
@admin_required
def admin_announcements():
    if request.method=="POST":
        title=request.form.get("title","").strip(); dept=request.form.get("department","General")
        kind=request.form.get("kind","Info"); audience=request.form.get("audience","All citizens"); body=request.form.get("body","").strip()
        if not title or not body: flash("Title and announcement details are required.", "error")
        else:
            db().execute("INSERT INTO announcements(title,department,kind,audience,body) VALUES(?,?,?,?,?)",(title,dept,kind,audience,body))
            db().commit(); flash("Announcement published.", "success"); return redirect(url_for("admin_announcements"))
    items=db().execute("SELECT * FROM announcements ORDER BY id DESC").fetchall()
    return render_template("admin_announcements.html",items=items)

@app.post("/admin/announcements/<int:item_id>/delete")
@admin_required
def delete_announcement(item_id):
    db().execute("DELETE FROM announcements WHERE id=?",(item_id,)); db().commit()
    flash("Announcement deleted.", "success"); return redirect(url_for("admin_announcements"))

@app.route("/admin/issues")
@admin_required
def admin_issues():
    status=request.args.get("status","All"); priority=request.args.get("priority","All")
    sql="SELECT i.*,c.first_name,c.last_name FROM issues i JOIN citizens c ON c.id=i.citizen_id WHERE 1=1"; params=[]
    if status!="All": sql+=" AND i.status=?"; params.append(status)
    if priority!="All": sql+=" AND i.priority=?"; params.append(priority)
    sql+=" ORDER BY CASE i.priority WHEN 'Emergency' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END, i.id DESC"
    items=db().execute(sql,params).fetchall()
    return render_template("issues.html",items=items,admin_view=True,status=status,priority=priority)

@app.post("/admin/issues/<int:item_id>/status")
@admin_required
def update_issue(item_id):
    status=request.form.get("status","Received")
    if status not in ("Received","In progress","Resolved"): status="Received"
    db().execute("UPDATE issues SET status=? WHERE id=?",(status,item_id)); db().commit()
    flash("Issue status updated.", "success"); return redirect(url_for("admin_issues"))

@app.route("/admin/payments")
@admin_required
def admin_payments():
    items=db().execute("SELECT p.*,c.first_name,c.last_name,c.email FROM payments p JOIN citizens c ON c.id=p.citizen_id ORDER BY p.id DESC").fetchall()
    total=db().execute("SELECT COALESCE(SUM(amount),0) FROM payments").fetchone()[0]
    return render_template("admin_payments.html",items=items,total=total)

@app.route("/health")
def health(): return {"status":"ok"}

with app.app_context(): init_db()
if __name__=="__main__": app.run(debug=os.environ.get("FLASK_DEBUG","0")=="0")
