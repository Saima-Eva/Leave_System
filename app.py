import io, os, secrets, sqlite3
from datetime import datetime, date, timedelta
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for, session,
                   send_file, flash, abort, g)
from werkzeug.security import generate_password_hash, check_password_hash
from docxtpl import DocxTemplate

BASE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(BASE, "leave_template.docx")
DB = os.path.join(BASE, "leaves.db")

app = Flask(__name__)
# Production-e SECRET_KEY environment variable set korben
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")

LEAVE_TYPES = ["Annual Leave", "Sick Leave", "Casual Leave", "Maternity Leave", "Unpaid Leave", "Other"]

# ---------- database ----------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d:
        d.close()

def init_db():
    with sqlite3.connect(DB) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'employee',
            emp_id TEXT, job_title TEXT, join_date TEXT);
        CREATE TABLE IF NOT EXISTS leaves(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, created TEXT NOT NULL,
            form_date TEXT, leave_type TEXT, start_date TEXT, end_date TEXT,
            leave_days INTEGER, return_date TEXT, address TEXT,
            replacement_name TEXT, manager_name TEXT,
            entitlement TEXT, entitlement_until TEXT, hr_leave_period TEXT,
            hr_period_until TEXT, leave_balance TEXT, approval TEXT DEFAULT '',
            FOREIGN KEY(user_id) REFERENCES users(id));
        """)
        if not c.execute("SELECT 1 FROM users WHERE role='hr'").fetchone():
            c.execute("INSERT INTO users(username,password_hash,full_name,role) VALUES(?,?,?,?)",
                      ("hr", generate_password_hash("hr12345"), "HR Admin", "hr"))
            print(">> Default HR login: hr / hr12345  (login korar por password change korben)")

# ---------- auth helpers ----------
def current_user():
    uid = session.get("uid")
    return db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone() if uid else None

def login_required(role=None):
    def deco(fn):
        @wraps(fn)
        def wrap(*a, **kw):
            u = current_user()
            if not u:
                return redirect(url_for("login"))
            if role and u["role"] != role:
                abort(403)
            g.user = u
            return fn(*a, **kw)
        return wrap
    return deco

@app.before_request
def csrf_protect():
    if request.method == "POST":
        if not session.get("csrf") or request.form.get("csrf") != session["csrf"]:
            abort(400, "Invalid CSRF token")

@app.context_processor
def inject():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return dict(csrf=session["csrf"], user=current_user())

# ---------- helpers ----------
def fmt(d):
    try:
        return datetime.strptime(d, "%Y-%m-%d").strftime("%d-%b-%Y")
    except (ValueError, TypeError):
        return d or ""

def status_of(row):
    return {"yes": "Approved", "no": "Rejected"}.get(row["approval"], "Pending")

def build_docx(leave_id):
    r = db().execute("""SELECT l.*, u.full_name, u.emp_id, u.job_title, u.join_date
                        FROM leaves l JOIN users u ON u.id=l.user_id WHERE l.id=?""", (leave_id,)).fetchone()
    if not r:
        abort(404)
    ctx = dict(r)
    ctx["emp_name"] = r["full_name"]
    for k in ("form_date", "join_date", "start_date", "end_date", "return_date",
              "entitlement_until", "hr_period_until"):
        ctx[k] = fmt(r[k])
    ctx["leave_days"] = f"{r['leave_days']} day(s)"
    ctx["yes_box"] = "☑" if r["approval"] == "yes" else "□"
    ctx["no_box"] = "☑" if r["approval"] == "no" else "□"
    for k, v in ctx.items():
        if v is None:
            ctx[k] = ""
    doc = DocxTemplate(TEMPLATE)
    doc.render(ctx)
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf, f"Leave_{r['emp_id'] or r['id']}_{r['start_date']}.docx"

# ---------- routes: common ----------
@app.route("/", methods=["GET"])
def home():
    u = current_user()
    if not u:
        return redirect(url_for("login"))
    return redirect(url_for("hr_dashboard" if u["role"] == "hr" else "my_leaves"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = db().execute("SELECT * FROM users WHERE username=?",
                         (request.form["username"].strip(),)).fetchone()
        if u and check_password_hash(u["password_hash"], request.form["password"]):
            session.clear()
            session["uid"] = u["id"]
            session["csrf"] = secrets.token_hex(16)
            return redirect(url_for("home"))
        flash("Username ba password vul.", "err")
    return render_template("login.html")

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/password", methods=["GET", "POST"])
@login_required()
def change_password():
    if request.method == "POST":
        if not check_password_hash(g.user["password_hash"], request.form["old"]):
            flash("Purono password vul.", "err")
        elif len(request.form["new"]) < 6:
            flash("Notun password kompokkhe 6 character hote hobe.", "err")
        else:
            db().execute("UPDATE users SET password_hash=? WHERE id=?",
                         (generate_password_hash(request.form["new"]), g.user["id"]))
            db().commit()
            flash("Password change hoyeche.", "ok")
            return redirect(url_for("home"))
    return render_template("password.html")

# ---------- routes: employee ----------
@app.route("/my-leaves")
@login_required("employee")
def my_leaves():
    rows = db().execute("SELECT * FROM leaves WHERE user_id=? ORDER BY id DESC", (g.user["id"],)).fetchall()
    return render_template("my_leaves.html", rows=rows, status_of=status_of, fmt=fmt)

@app.route("/apply", methods=["GET", "POST"])
@login_required("employee")
def apply():
    if request.method == "POST":
        f = request.form
        try:
            s = datetime.strptime(f["start_date"], "%Y-%m-%d").date()
            e = datetime.strptime(f["end_date"], "%Y-%m-%d").date()
        except ValueError:
            flash("Date thik moto din.", "err")
            return redirect(url_for("apply"))
        if e < s:
            flash("Leave End date, Start date er age hote pare na.", "err")
            return redirect(url_for("apply"))
        days = (e - s).days + 1
        ret = e + timedelta(days=1)
        db().execute("""INSERT INTO leaves(user_id,created,form_date,leave_type,start_date,end_date,
                        leave_days,return_date,address) VALUES(?,?,?,?,?,?,?,?,?)""",
                     (g.user["id"], datetime.now().isoformat(timespec="seconds"),
                      date.today().isoformat(), f["leave_type"], s.isoformat(), e.isoformat(),
                      days, ret.isoformat(), f["address"].strip()))
        db().commit()
        flash("Leave request submit hoyeche. HR review korbe.", "ok")
        return redirect(url_for("my_leaves"))
    return render_template("apply.html", types=LEAVE_TYPES, today=date.today().isoformat())

# ---------- routes: HR ----------
@app.route("/hr")
@login_required("hr")
def hr_dashboard():
    q = request.args.get("status", "")
    rows = db().execute("""SELECT l.*, u.full_name, u.emp_id FROM leaves l
                           JOIN users u ON u.id=l.user_id ORDER BY l.id DESC""").fetchall()
    if q:
        rows = [r for r in rows if status_of(r) == q]
    return render_template("hr_dashboard.html", rows=rows, status_of=status_of, fmt=fmt, q=q)

@app.route("/hr/leave/<int:lid>", methods=["GET", "POST"])
@login_required("hr")
def hr_edit(lid):
    r = db().execute("""SELECT l.*, u.full_name, u.emp_id, u.job_title FROM leaves l
                        JOIN users u ON u.id=l.user_id WHERE l.id=?""", (lid,)).fetchone()
    if not r:
        abort(404)
    if request.method == "POST":
        f = request.form
        cols = ["replacement_name", "manager_name", "entitlement", "entitlement_until",
                "hr_leave_period", "hr_period_until", "leave_balance", "approval"]
        vals = [f.get(c, "").strip() for c in cols]
        db().execute(f"UPDATE leaves SET {','.join(c+'=?' for c in cols)} WHERE id=?", vals + [lid])
        db().commit()
        flash("Update hoyeche.", "ok")
        return redirect(url_for("hr_edit", lid=lid))
    return render_template("hr_edit.html", r=r, fmt=fmt, status=status_of(r))

@app.route("/hr/download/<int:lid>")
@login_required("hr")
def hr_download(lid):
    buf, name = build_docx(lid)
    return send_file(buf, as_attachment=True, download_name=name,
                     mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

@app.route("/hr/employees", methods=["GET", "POST"])
@login_required("hr")
def hr_employees():
    if request.method == "POST":
        f = request.form
        try:
            db().execute("""INSERT INTO users(username,password_hash,full_name,role,emp_id,job_title,join_date)
                            VALUES(?,?,?,'employee',?,?,?)""",
                         (f["username"].strip(), generate_password_hash(f["password"]), f["full_name"].strip(),
                          f["emp_id"].strip(), f["job_title"].strip(), f["join_date"]))
            db().commit()
            flash("Employee add hoyeche.", "ok")
        except sqlite3.IntegrityError:
            flash("Ei username age thekei ache.", "err")
        return redirect(url_for("hr_employees"))
    rows = db().execute("SELECT * FROM users WHERE role='employee' ORDER BY full_name").fetchall()
    return render_template("hr_employees.html", rows=rows, fmt=fmt)

init_db()
if __name__ == "__main__":
    app.run(debug=True, port=5000)
