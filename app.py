from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from database.database import get_db, create_tables

app = Flask(__name__)
app.secret_key = "class-secret-key"

create_tables()


FLOORS = [
    {"number": 1, "title": "1st Floor", "rooms": ["101", "102", "103", "104", "105"]},
    {"number": 2, "title": "2nd Floor", "rooms": ["201", "202", "203", "204", "205"]},
    {"number": 3, "title": "3rd Floor", "rooms": ["301", "302", "303", "304", "305"]},
    {"number": 4, "title": "4th Floor", "rooms": ["Seminar Hall"]},
]
ALL_ROOMS = []
for f in FLOORS:
    ALL_ROOMS = ALL_ROOMS + f["rooms"]
TOTAL_ROOMS = len(ALL_ROOMS)

MAX_YEAR = 5        
MAX_CLASSES = 12    


def room_label(room):
    """'101' -> 'Room 101', 'Seminar Hall' -> 'Seminar Hall'"""
    if not room:
        return "Not allotted"
    return "Room " + room if room.isdigit() else room


def year_label(number):
    """2 -> '2nd Year'"""
    if not number:
        return ""
    ending = {1: "st", 2: "nd", 3: "rd"}.get(number, "th")
    return str(number) + ending + " Year"


def class_label(department, year_no, section):
    """('CSE', 2, 'D1') -> 'CSE 2nd Year D1'"""
    parts = [department or "", year_label(year_no), section or ""]
    return " ".join(p for p in parts if p != "")


def make_slots(items):
    slots = []
    number = 0
    for kind, start, end in items:
        if kind == "period":
            number = number + 1
            name = "Period " + str(number)
        else:
            name = "Break"
        slots.append({"type": kind, "name": name, "start": start, "end": end,
                      "key": start + "-" + end})
    return slots


THIRD_YEAR = make_slots([
    ("period", "09:30", "10:20"),
    ("period", "10:20", "11:10"),
    ("period", "11:20", "12:10"),
    ("period", "12:10", "13:00"),
    ("period", "14:00", "14:50"),
    ("period", "14:50", "15:40"),
    ("period", "15:40", "16:30"),
])
PERIODS = {
    "2": make_slots([
        ("period", "09:30", "10:20"),
        ("period", "10:20", "11:10"),
        ("period", "11:20", "12:10"),
        ("period", "12:10", "13:00"),
        ("period", "13:30", "14:20"),
        ("period", "15:10", "16:00"),
    ]),
    "3": THIRD_YEAR,
    "default": THIRD_YEAR,
}


def get_periods(year_no):
    return PERIODS.get(str(year_no), PERIODS["default"])


app.add_template_filter(room_label, "room_label")
app.add_template_filter(year_label, "year_label")


@app.template_filter("nice_date")
def nice_date(text):
    try:
        return datetime.strptime(text, "%Y-%m-%d").strftime("%d %b %Y")
    except (ValueError, TypeError):
        return text


@app.template_filter("nice_time")
def nice_time(text):
    try:
        return datetime.strptime(text, "%H:%M").strftime("%I:%M %p").lstrip("0")
    except (ValueError, TypeError):
        return text


def split_names(text):
    """'Mr Rao, Ms Devi' -> ['Mr Rao', 'Ms Devi'] (old bookings could have several teachers)"""
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip() != ""]


def clean(text):
    """Removes extra spaces."""
    return " ".join((text or "").split())


def to_int(text):
    try:
        return int(text)
    except (ValueError, TypeError):
        return None


def get_departments():
    """Every department with its years: [{id, name, years: [{year_no, label, count, classes}]}]"""
    db = get_db()
    departments = db.execute("SELECT * FROM departments ORDER BY name COLLATE NOCASE").fetchall()
    years = db.execute("SELECT * FROM department_years ORDER BY year_no").fetchall()
    db.close()

    result = []
    for d in departments:
        year_list = []
        for y in years:
            if y["department_id"] == d["id"]:
                year_list.append({"year_no": y["year_no"], "label": year_label(y["year_no"]),
                                  "count": y["class_count"],
                                  "classes": ["D" + str(n) for n in range(1, y["class_count"] + 1)]})
        result.append({"id": d["id"], "name": d["name"], "years": year_list})
    return result


def find_department(departments, department_id):
    for d in departments:
        if d["id"] == department_id:
            return d
    return None


def find_year(department, year_no):
    if department:
        for y in department["years"]:
            if y["year_no"] == year_no:
                return y
    return None


def get_teachers():
    """Every teacher with what he or she teaches: [{id, name, entries: [...]}]"""
    db = get_db()
    teachers = db.execute("SELECT * FROM teachers ORDER BY name COLLATE NOCASE").fetchall()
    entries = db.execute("""SELECT ts.id, ts.teacher_id, ts.department_id, ts.year_no, ts.subject,
                                   d.name AS department
                            FROM teacher_subjects ts
                            LEFT JOIN departments d ON d.id = ts.department_id
                            ORDER BY ts.id""").fetchall()
    db.close()

    result = []
    for t in teachers:
        mine = []
        for e in entries:
            if e["teacher_id"] == t["id"]:
                mine.append({"department_id": e["department_id"], "department": e["department"] or "",
                             "year_no": e["year_no"], "year": year_label(e["year_no"]),
                             "subject": e["subject"]})
        groups = []
        for e in mine:
            for g in groups:
                if g["department_id"] == e["department_id"] and g["subject"].lower() == e["subject"].lower():
                    g["years"].append(e["year"])
                    break
            else:
                groups.append({"department_id": e["department_id"], "department": e["department"],
                               "subject": e["subject"], "years": [e["year"]]})
        for g in groups:
            g["years_text"] = ", ".join(g["years"])
        result.append({"id": t["id"], "name": t["name"], "entries": mine, "groups": groups})
    return result


def today_text():
    return datetime.now().strftime("%Y-%m-%d")


def now_time_text():
    return datetime.now().strftime("%H:%M")


def get_state(b):
    """Ongoing / Upcoming / Completed / Ended for one booking row."""
    if b["status"] == "Ended":
        return "Ended"
    today = today_text()
    now = now_time_text()
    if b["date"] < today:
        return "Completed"
    if b["date"] > today:
        return "Upcoming"
    if b["end_time"] <= now:
        return "Completed"
    if b["start_time"] <= now:
        return "Ongoing"
    return "Upcoming"


def booking_periods(b):
    """Period names a booking is in: its saved period, else the periods its clock time touches."""
    if b["period"]:
        return [b["period"]]
    names = []
    for p in get_periods(b["year_no"]):
        if p["type"] == "period" and b["start_time"] < p["end"] and b["end_time"] > p["start"]:
            names.append(p["name"])
    return names


STATE_LABELS = {"Ongoing": "Running", "Upcoming": "Upcoming", "Completed": "Done", "Ended": "Done"}
STATE_PILLS = {"Ongoing": "confirmed", "Upcoming": "pending", "Completed": "done", "Ended": "done"}


def with_state(rows):
    result = []
    for row in rows:
        item = dict(row)
        item["state"] = get_state(row)
        item["label"] = STATE_LABELS[item["state"]]
        item["pill"] = STATE_PILLS[item["state"]]
        item["periods"] = booking_periods(row)
        item["period_text"] = ", ".join(item["periods"])
        item["class_label"] = class_label(row["department"], row["year_no"], row["section"])
        item["room_text"] = room_label(row["room"])
        result.append(item)
    return result


STATE_RANK = {"Ongoing": 0, "Upcoming": 1, "Completed": 2, "Ended": 2}


def sort_by_time(rows):
    """Running now first, then coming up (soonest first), finished classes at the bottom
    (the one that finished most recently is the highest of those)."""
    live = [b for b in rows if STATE_RANK[b["state"]] < 2]
    done = [b for b in rows if STATE_RANK[b["state"]] == 2]
    live.sort(key=lambda b: (STATE_RANK[b["state"]], b["date"], b["start_time"], b["room"]))
    done.sort(key=lambda b: (b["date"], b["end_time"], b["room"]), reverse=True)
    return live + done


def time_label(b):
    """'Period 2 - 10:20 AM - 11:10 AM' or just the time for a manual booking."""
    text = nice_time(b["start_time"]) + " - " + nice_time(b["end_time"])
    return (b["period_text"] + " \u00b7 " + text) if b["period_text"] else text


app.add_template_filter(time_label, "time_label")


def get_today_rows():
    db = get_db()
    rows = db.execute("SELECT * FROM bookings WHERE date = ?", (today_text(),)).fetchall()
    db.close()
    return sort_by_time(with_state(rows))


def get_room_status():
    """Today's status of every room: which class is inside now, and what is next."""
    db = get_db()
    rows = db.execute("SELECT * FROM bookings WHERE date = ? ORDER BY start_time",
                      (today_text(),)).fetchall()
    db.close()
    today_rows = with_state(rows)

    floors = []
    free = 0
    in_use = 0
    for f in FLOORS:
        room_items = []
        for room in f["rooms"]:
            classes = [b for b in today_rows if b["room"] == room and b["state"] != "Ended"]
            current = None
            upcoming = []
            for b in classes:
                if b["state"] == "Ongoing":
                    current = b
                elif b["state"] == "Upcoming":
                    upcoming.append(b)
            if current:
                in_use = in_use + 1
            else:
                free = free + 1
            room_items.append({"name": room, "label": room_label(room), "current": current,
                               "next": upcoming[0] if upcoming else None})
        floors.append({"number": f["number"], "title": f["title"], "rooms": room_items})
    return floors, free, in_use, today_rows


@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form["full_name"].strip()
        email = request.form["email"].strip().lower()
        username = request.form["username"].strip()
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if full_name == "" or email == "" or username == "" or password == "":
            flash("Please fill in all the fields.", "error")
            return redirect(url_for("register"))

        if "@" not in email or "." not in email:
            flash("Please enter a valid email.", "error")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return redirect(url_for("register"))

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("register"))

        db = get_db()
        old_user = db.execute("SELECT id FROM users WHERE username = ? OR email = ?",
                              (username, email)).fetchone()
        if old_user:
            db.close()
            flash("That username or email is already used.", "error")
            return redirect(url_for("register"))

        password_hash = generate_password_hash(password, method="pbkdf2:sha256")
        db.execute("INSERT INTO users (full_name, email, username, password_hash) VALUES (?, ?, ?, ?)",
                   (full_name, email, username, password_hash))
        db.commit()
        db.close()

        flash("Account created! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        name = request.form["login_name"].strip()
        password = request.form["password"]

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ? OR email = ?",
                          (name, name.lower())).fetchone()
        db.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["full_name"] = user["full_name"]
            return redirect(url_for("dashboard"))

        flash("Wrong username/email or password.", "error")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You are logged out.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    floors, free, in_use, unused = get_room_status()

    db = get_db()
    total_bookings = db.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
    total_teachers = db.execute("SELECT COUNT(*) FROM teachers").fetchone()[0]
    total_departments = db.execute("SELECT COUNT(*) FROM departments").fetchone()[0]
    db.close()

    today_rows = get_today_rows()
    free_percent = round(free * 100 / TOTAL_ROOMS)

    return render_template("dashboard.html",
                           first_name=session["full_name"].split()[0],
                           today=datetime.now().strftime("%A, %d %B %Y"),
                           total_rooms=TOTAL_ROOMS,
                           free=free,
                           in_use=in_use,
                           free_percent=free_percent,
                           classes_today=len(today_rows),
                           total_bookings=total_bookings,
                           total_teachers=total_teachers,
                           total_departments=total_departments,
                           todays_classes=today_rows)


# =====================================================================
#  DEPARTMENTS  (name + years + number of classes in every year)
# =====================================================================
def read_department_form(form):
    """Returns (name, years, error). years = [{'year_no': 2, 'count': 3}, ...]"""
    name = clean(form.get("name", ""))
    years = []
    seen = []
    for year_text, count_text in zip(form.getlist("year_no"), form.getlist("class_count")):
        if clean(year_text) == "" and clean(count_text) == "":
            continue
        year_no = to_int(year_text)
        count = to_int(count_text)
        if year_no is None or year_no < 1 or year_no > MAX_YEAR:
            return name, years, "Please choose a year from 1st to " + year_label(MAX_YEAR) + "."
        if count is None or count < 1 or count > MAX_CLASSES:
            return name, years, "Number of classes must be from 1 to " + str(MAX_CLASSES) + "."
        if year_no in seen:
            return name, years, year_label(year_no) + " is added twice. Please add it only once."
        seen.append(year_no)
        years.append({"year_no": year_no, "count": count})
    years.sort(key=lambda y: y["year_no"])

    if name == "":
        return name, years, "Please enter the department name."
    return name, years, None


def department_name_taken(name, ignore_id=0):
    db = get_db()
    row = db.execute("SELECT id FROM departments WHERE name = ? AND id != ?", (name, ignore_id)).fetchone()
    db.close()
    return row is not None


@app.route("/departments")
def departments():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("departments.html", departments=get_departments())


@app.route("/departments/add", methods=["GET", "POST"])
def add_department():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        name, years, error = read_department_form(request.form)
        if error is None and department_name_taken(name):
            error = name + " is already added."
        if error:
            flash(error, "error")
            return render_template("department_form.html", dept={"name": name, "years": years},
                                   editing=False, max_year=MAX_YEAR, max_classes=MAX_CLASSES)

        db = get_db()
        cursor = db.execute("INSERT INTO departments (name) VALUES (?)", (name,))
        for y in years:
            db.execute("INSERT INTO department_years (department_id, year_no, class_count) VALUES (?, ?, ?)",
                       (cursor.lastrowid, y["year_no"], y["count"]))
        db.commit()
        db.close()

        flash(name + " department added.", "success")
        return redirect(url_for("departments"))

    return render_template("department_form.html", dept={"name": "", "years": [{"year_no": 1, "count": 3}]},
                           editing=False, max_year=MAX_YEAR, max_classes=MAX_CLASSES)


@app.route("/departments/edit/<int:id>", methods=["GET", "POST"])
def edit_department(id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    department = find_department(get_departments(), id)
    if department is None:
        flash("Department not found.", "error")
        return redirect(url_for("departments"))

    if request.method == "POST":
        name, years, error = read_department_form(request.form)
        if error is None and department_name_taken(name, id):
            error = name + " is already added."
        if error:
            flash(error, "error")
            return render_template("department_form.html", dept={"id": id, "name": name, "years": years},
                                   editing=True, max_year=MAX_YEAR, max_classes=MAX_CLASSES)

        db = get_db()
        db.execute("UPDATE departments SET name = ? WHERE id = ?", (name, id))
        # old bookings keep showing the right department name
        db.execute("UPDATE bookings SET department = ? WHERE department = ?", (name, department["name"]))

        db.execute("DELETE FROM department_years WHERE department_id = ?", (id,))
        for y in years:
            db.execute("INSERT INTO department_years (department_id, year_no, class_count) VALUES (?, ?, ?)",
                       (id, y["year_no"], y["count"]))

        # a year that was removed can no longer be taught by teachers
        kept = [y["year_no"] for y in years]
        removed = [y["year_no"] for y in department["years"] if y["year_no"] not in kept]
        for year_no in removed:
            db.execute("DELETE FROM teacher_subjects WHERE department_id = ? AND year_no = ?", (id, year_no))
        db.commit()
        db.close()

        flash(name + " department updated.", "success")
        return redirect(url_for("departments"))

    dept = {"id": id, "name": department["name"],
            "years": [{"year_no": y["year_no"], "count": y["count"]} for y in department["years"]]}
    return render_template("department_form.html", dept=dept, editing=True,
                           max_year=MAX_YEAR, max_classes=MAX_CLASSES)


@app.route("/departments/delete/<int:id>", methods=["POST"])
def delete_department(id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    db = get_db()
    db.execute("DELETE FROM department_years WHERE department_id = ?", (id,))
    db.execute("DELETE FROM teacher_subjects WHERE department_id = ?", (id,))
    db.execute("DELETE FROM departments WHERE id = ?", (id,))
    db.commit()
    db.close()

    flash("Department deleted.", "success")
    return redirect(url_for("departments"))


# =====================================================================
#  TEACHERS  (name + department + year + subject)
# =====================================================================
def read_teacher_form(form):
    """Returns (name, entries, error). entries = [{'department_id', 'year_no', 'subject'}]
    One row of the form = one department + one subject + one or more years."""
    name = clean(form.get("name", "").replace(",", " "))
    all_departments = get_departments()
    entries = []
    seen = []

    for row in form.getlist("row"):
        department_text = form.get("department_" + row, "")
        subject = clean(form.get("subject_" + row, ""))
        year_texts = form.getlist("years_" + row)
        if department_text == "" and subject == "" and not year_texts:
            continue
        department_id = to_int(department_text)
        department = find_department(all_departments, department_id)
        if department is None or subject == "" or not year_texts:
            return name, entries, "Please choose the department, at least one year and the subject in every row (or remove the row)."
        for year_text in year_texts:
            year_no = to_int(year_text)
            if find_year(department, year_no) is None:
                return name, entries, "Please choose the years of the selected department."
            key = (department_id, year_no, subject.lower())
            if key not in seen:
                seen.append(key)
                entries.append({"department_id": department_id, "year_no": year_no, "subject": subject})

    if name == "":
        return name, entries, "Please enter the teacher name."
    if not entries:
        return name, entries, "Please add the department, year and subject this teacher will teach."
    return name, entries, None


def teacher_name_taken(name, ignore_id=0):
    db = get_db()
    row = db.execute("SELECT id FROM teachers WHERE name = ? AND id != ?", (name, ignore_id)).fetchone()
    db.close()
    return row is not None


def save_entries(db, teacher_id, entries):
    db.execute("DELETE FROM teacher_subjects WHERE teacher_id = ?", (teacher_id,))
    for e in entries:
        db.execute("""INSERT INTO teacher_subjects (teacher_id, department_id, year_no, subject)
                      VALUES (?, ?, ?, ?)""", (teacher_id, e["department_id"], e["year_no"], e["subject"]))


@app.route("/teachers")
def teachers():
    if "user_id" not in session:
        return redirect(url_for("login"))

    today_rows = get_today_rows()
    people = []
    for t in get_teachers():
        mine = [b for b in today_rows if t["name"].lower() in [n.lower() for n in split_names(b["teacher_name"])]]
        t["count"] = len(mine)
        t["classes"] = mine
        people.append(t)

    chosen = None
    selected = to_int(request.args.get("id", ""))
    for person in people:
        if person["id"] == selected:
            chosen = person

    return render_template("teachers.html", people=people, chosen=chosen,
                           today=datetime.now().strftime("%A, %d %B %Y"))


@app.route("/teachers/add", methods=["GET", "POST"])
def add_teacher():
    if "user_id" not in session:
        return redirect(url_for("login"))

    all_departments = get_departments()

    if request.method == "POST":
        name, entries, error = read_teacher_form(request.form)
        if error is None and teacher_name_taken(name):
            error = name + " is already added. Use Edit to change the details."
        if error:
            flash(error, "error")
            return render_template("teacher_form.html", teacher={"name": name, "entries": entries},
                                   departments=all_departments, editing=False)

        db = get_db()
        cursor = db.execute("INSERT INTO teachers (name) VALUES (?)", (name,))
        save_entries(db, cursor.lastrowid, entries)
        db.commit()
        db.close()

        flash(name + " added.", "success")
        return redirect(url_for("teachers"))

    return render_template("teacher_form.html", teacher={"name": "", "entries": []},
                           departments=all_departments, editing=False)


@app.route("/teachers/edit/<int:id>", methods=["GET", "POST"])
def edit_teacher(id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    all_departments = get_departments()
    teacher = None
    for t in get_teachers():
        if t["id"] == id:
            teacher = t
    if teacher is None:
        flash("Teacher not found.", "error")
        return redirect(url_for("teachers"))

    if request.method == "POST":
        name, entries, error = read_teacher_form(request.form)
        if error is None and teacher_name_taken(name, id):
            error = name + " is already added."
        if error:
            flash(error, "error")
            return render_template("teacher_form.html", teacher={"id": id, "name": name, "entries": entries},
                                   departments=all_departments, editing=True)

        db = get_db()
        db.execute("UPDATE teachers SET name = ? WHERE id = ?", (name, id))
        # old bookings keep showing the right teacher name
        db.execute("UPDATE bookings SET teacher_name = ? WHERE teacher_name = ?", (name, teacher["name"]))
        save_entries(db, id, entries)
        db.commit()
        db.close()

        flash(name + " updated.", "success")
        return redirect(url_for("teachers"))

    return render_template("teacher_form.html", teacher=teacher, departments=all_departments, editing=True)


@app.route("/teachers/delete/<int:id>", methods=["POST"])
def delete_teacher(id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    db = get_db()
    db.execute("DELETE FROM teacher_subjects WHERE teacher_id = ?", (id,))
    db.execute("DELETE FROM teachers WHERE id = ?", (id,))
    db.commit()
    db.close()

    flash("Teacher deleted.", "success")
    return redirect(url_for("teachers"))


@app.route("/rooms")
def rooms():
    if "user_id" not in session:
        return redirect(url_for("login"))

    floors, free, in_use, today_rows = get_room_status()
    return render_template("rooms.html", floors=floors, total_rooms=TOTAL_ROOMS,
                           free=free, in_use=in_use,
                           now=datetime.now().strftime("%I:%M %p").lstrip("0"))


@app.route("/schedule")
def schedule():
    if "user_id" not in session:
        return redirect(url_for("login"))

    search = request.args.get("search", "").strip()
    date = request.args.get("date", "").strip()
    room = request.args.get("room", "").strip()
    department = request.args.get("department", "").strip()

    sql = "SELECT * FROM bookings WHERE 1 = 1"
    values = []
    if search != "":
        sql = sql + " AND (teacher_name LIKE ? OR subject LIKE ? OR department LIKE ?)"
        values = values + ["%" + search + "%"] * 3
    if date != "":
        sql = sql + " AND date = ?"
        values.append(date)
    if room != "":
        sql = sql + " AND room = ?"
        values.append(room)
    if department != "":
        # "CSE" = whole department, "CSE|2|D1" = one class
        parts = department.rsplit("|", 2)
        if len(parts) == 3 and to_int(parts[1]) is not None:
            sql = sql + " AND department = ? AND year_no = ? AND section = ?"
            values += [parts[0], to_int(parts[1]), parts[2]]
        else:
            sql = sql + " AND department = ?"
            values.append(department)

    db = get_db()
    rows = db.execute(sql, values).fetchall()
    db.close()
    department_names = get_departments()

    return render_template("schedule.html", department=department, department_names=department_names, bookings=sort_by_time(with_state(rows)), search=search,
                           date=date, room=room, floors=FLOORS)


def clash_text(row, what):
    return (what + " is already busy from " + nice_time(row["start_time"]) + " to "
            + nice_time(row["end_time"]) + " (" + class_label(row["department"], row["year_no"], row["section"])
            + " with " + row["teacher_name"] + ", " + room_label(row["room"]) + ").")


def find_clash(where_sql, values, date, start_time, end_time, ignore_id):
    db = get_db()
    row = db.execute("""SELECT * FROM bookings
                        WHERE """ + where_sql + """ AND date = ? AND status = 'Scheduled'
                        AND id != ? AND start_time < ? AND end_time > ?""",
                     tuple(values) + (date, ignore_id, end_time, start_time)).fetchone()
    db.close()
    return row


def read_booking(form, ignore_id=0):
    """Reads the allot form. Returns (data, error)."""
    data = {"room": form.get("room", "").strip(),
            "teacher_id": to_int(form.get("teacher_id", "")),
            "department_id": to_int(form.get("department_id", "")),
            "year_no": to_int(form.get("year_no", "")),
            "section": form.get("section", "").strip(),
            "subject": clean(form.get("subject", "")),
            "date": form.get("date", "").strip(),
            "mode": form.get("mode", "manual"),
            "period": form.get("period", ""),
            "start_time": form.get("start_time", ""),
            "end_time": form.get("end_time", ""),
            "period_name": "", "teacher_name": "", "department": ""}

    if data["room"] not in ALL_ROOMS:
        return data, "Please select a room."

    teacher = None
    for t in get_teachers():
        if t["id"] == data["teacher_id"]:
            teacher = t
    if teacher is None:
        return data, "Please select a teacher."
    data["teacher_name"] = teacher["name"]

    department = find_department(get_departments(), data["department_id"])
    if department is None:
        return data, "Please select a department."
    year = find_year(department, data["year_no"])
    if year is None:
        return data, "Please select a year."
    if data["section"] not in year["classes"]:
        return data, "Please select a class (" + ", ".join(year["classes"]) + ")."
    data["department"] = department["name"]

    if data["subject"] == "":
        return data, "Please enter the subject."
    if data["date"] == "":
        return data, "Please select the date."

    if data["mode"] == "period":
        found = False
        for p in get_periods(data["year_no"]):
            if p["type"] == "period" and p["key"] == data["period"]:
                data["start_time"], data["end_time"], data["period_name"] = p["start"], p["end"], p["name"]
                found = True
        if not found:
            return data, "Please select a period."

    start_time, end_time, date = data["start_time"], data["end_time"], data["date"]
    if start_time == "" or end_time == "":
        return data, "Please select the time."
    try:
        datetime.strptime(date, "%Y-%m-%d")
        datetime.strptime(start_time, "%H:%M")
        datetime.strptime(end_time, "%H:%M")
    except ValueError:
        return data, "Please enter a valid date and time."
    if end_time <= start_time:
        return data, "End time must be after the start time."
    if date < today_text():
        return data, "You cannot allot a room for a past date."
    if date == today_text() and end_time <= now_time_text():
        return data, "That time is already over. Please choose a later time."

    # the room, the teacher and the class can only be in one place at a time
    clash = find_clash("room = ?", (data["room"],), date, start_time, end_time, ignore_id)
    if clash:
        return data, clash_text(clash, room_label(data["room"]))
    clash = find_clash("teacher_name = ?", (data["teacher_name"],), date, start_time, end_time, ignore_id)
    if clash:
        return data, clash_text(clash, data["teacher_name"])
    clash = find_clash("department = ? AND year_no = ? AND section = ?",
                       (data["department"], data["year_no"], data["section"]),
                       date, start_time, end_time, ignore_id)
    if clash:
        return data, clash_text(clash, class_label(data["department"], data["year_no"], data["section"]))

    return data, None


def show_booking_form(form, editing, booking_id=0):
    return render_template("booking_form.html", form=form, floors=FLOORS, departments=get_departments(),
                           teachers=get_teachers(), periods=PERIODS, editing=editing, booking_id=booking_id)


@app.route("/schedule/add", methods=["GET", "POST"])
def add_booking():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        data, error = read_booking(request.form)
        if error:
            flash(error, "error")
            return show_booking_form(data, False)

        db = get_db()
        db.execute("""INSERT INTO bookings (teacher_name, room, date, start_time, end_time, period,
                                            department, year_no, section, subject)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                   (data["teacher_name"], data["room"], data["date"], data["start_time"], data["end_time"],
                    data["period_name"], data["department"], data["year_no"], data["section"], data["subject"]))
        db.commit()
        db.close()

        flash(room_label(data["room"]) + " allotted to " + data["teacher_name"] + " for "
              + class_label(data["department"], data["year_no"], data["section"]) + ".", "success")
        return redirect(url_for("schedule"))

    form = {"room": request.args.get("room", ""), "teacher_id": None, "department_id": None,
            "year_no": None, "section": "", "subject": "", "date": today_text(),
            "mode": "manual", "period": "", "start_time": "", "end_time": ""}
    return show_booking_form(form, False)


@app.route("/schedule/edit/<int:id>", methods=["GET", "POST"])
def edit_booking(id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    db = get_db()
    booking = db.execute("SELECT * FROM bookings WHERE id = ?", (id,)).fetchone()
    db.close()

    if booking is None:
        flash("Booking not found.", "error")
        return redirect(url_for("schedule"))

    if request.method == "POST":
        data, error = read_booking(request.form, id)
        if error:
            flash(error, "error")
            return show_booking_form(data, True, id)

        db = get_db()
        db.execute("""UPDATE bookings SET teacher_name = ?, room = ?, date = ?, start_time = ?, end_time = ?,
                      period = ?, department = ?, year_no = ?, section = ?, subject = ?, status = 'Scheduled'
                      WHERE id = ?""",
                   (data["teacher_name"], data["room"], data["date"], data["start_time"], data["end_time"],
                    data["period_name"], data["department"], data["year_no"], data["section"],
                    data["subject"], id))
        db.commit()
        db.close()

        flash("Booking updated.", "success")
        return redirect(url_for("schedule"))

    # fill the form from the saved booking
    teacher_id = None
    for t in get_teachers():
        if t["name"].lower() == (booking["teacher_name"] or "").lower():
            teacher_id = t["id"]
    department_id = None
    for d in get_departments():
        if d["name"].lower() == (booking["department"] or "").lower():
            department_id = d["id"]

    form = {"room": booking["room"], "teacher_id": teacher_id, "department_id": department_id,
            "year_no": booking["year_no"], "section": booking["section"], "subject": booking["subject"],
            "date": booking["date"], "mode": "period" if booking["period"] else "manual",
            "period": booking["start_time"] + "-" + booking["end_time"] if booking["period"] else "",
            "start_time": booking["start_time"], "end_time": booking["end_time"]}
    return show_booking_form(form, True, id)


@app.route("/schedule/end/<int:id>", methods=["POST"])
def end_class(id):
    """The class is over (teacher is leaving early): the room becomes free right now."""
    if "user_id" not in session:
        return redirect(url_for("login"))

    db = get_db()
    booking = db.execute("SELECT * FROM bookings WHERE id = ?", (id,)).fetchone()

    if booking is None:
        db.close()
        flash("Booking not found.", "error")
        return redirect(request.referrer or url_for("schedule"))

    if get_state(booking) != "Ongoing":
        db.close()
        flash("Only a class that is running now can be ended.", "error")
        return redirect(request.referrer or url_for("schedule"))

    end_now = max(now_time_text(), booking["start_time"])
    db.execute("UPDATE bookings SET status = 'Ended', end_time = ? WHERE id = ?", (end_now, id))
    db.commit()
    db.close()

    flash("Class ended. " + room_label(booking["room"]) + " is free now.", "success")
    return redirect(request.referrer or url_for("schedule"))


@app.route("/schedule/delete/<int:id>", methods=["POST"])
def delete_booking(id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    db = get_db()
    db.execute("DELETE FROM bookings WHERE id = ?", (id,))
    db.commit()
    db.close()

    flash("Booking deleted.", "success")
    return redirect(request.referrer or url_for("schedule"))


if __name__ == "__main__":
    app.run(debug=True)
