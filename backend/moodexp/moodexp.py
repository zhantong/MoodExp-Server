from flask import Flask
from flask import send_from_directory
from flask import request
from flask import g
from flask import render_template
from werkzeug.utils import secure_filename
import json
import os
import shutil
import sqlite3
import uuid

app = Flask(__name__)

FILENAME_BACKUP = 'backup'
FILENAME_UPLOAD = 'uploads'
FILENAME_SECONDARY_BACKUP = 'second_backup'
DATABASE = 'moodexp.db'


@app.route('/uploads/<path:filename>', methods=['GET'])
def download_file(filename):
    return send_from_directory(FILENAME_UPLOAD, filename)


@app.route('/register', methods=['GET'])
def register():
    class_name = request.args.get('class')
    name = request.args.get('name')
    student_id = request.args.get('id')
    phone = request.args.get('phone')

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT count(*) FROM users WHERE id = ?", (student_id,))
    count = c.fetchone()[0]
    if count == 0:
        c.execute("INSERT INTO users VALUES (?,?,?,?)",
                  (class_name, name, student_id, phone))
        conn.commit()
        return json.dumps({'status': True})
    return json.dumps({'status': False})


@app.route('/info', methods=['GET'])
def info():
    student_id = request.args.get('id')
    conn = get_db()
    conn.row_factory = dict_factory
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (student_id,))
    info = c.fetchall()
    if info:
        info = info[0]
        info['status'] = True
        return json.dumps(info)
    else:
        return json.dumps({'status': False})


@app.route('/delete', methods=['GET'])
def delete():
    student_id = request.args.get('id')
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ?", (student_id,))
    c.execute("DELETE FROM uploads WHERE id = ?", (student_id,))
    conn.commit()
    return json.dumps({'status': True})


@app.route('/upload', methods=['POST'])
def upload():
    f = request.files['file']
    orig_filename = request.form['filename']
    #orig_filename = f.filename
    f.save(FILENAME_BACKUP + '/' + orig_filename)
    student_id, count, file_ext = split_filename(orig_filename)
    shutil.copyfile(FILENAME_BACKUP + '/' + orig_filename,
                    FILENAME_UPLOAD + '/' + student_id + '.' + file_ext)

    random_filename = str(uuid.uuid4())
    shutil.copyfile(FILENAME_BACKUP + '/' + orig_filename,
                    FILENAME_SECONDARY_BACKUP + '/' + random_filename)

    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO uploads VALUES (?,?)", (student_id, int(count)))
    c.execute("INSERT INTO second_backup (id,count,filename) VALUES (?,?,?)",
              (student_id, int(count), random_filename))
    conn.commit()
    return json.dumps({'status': True})


@app.route('/statistic', methods=['GET'])
def statistic():
    rows = get_statistic()
    return json.dumps(rows)


@app.route('/stat', methods=['GET'])
def stat():
    rows = get_statistic()
    return render_template('stat.html', students=rows)


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db


def split_filename(filename):
    return filename.replace('_', ' ').replace('.', ' ').split()


def get_statistic():
    with app.app_context():
        users = []
        conn = get_db()
        conn.row_factory = dict_factory
        c = conn.cursor()
        c.execute("SELECT * FROM users")
        rows = c.fetchall()
        for row in rows:
            student_id = row['id']
            c.execute(
                "SELECT count FROM uploads WHERE id = ? ORDER BY count ASC", (student_id,))
            row['count'] = [x['count'] for x in c.fetchall()]
        return rows


def init():
    create_dir_if_not_exists(FILENAME_BACKUP)
    create_dir_if_not_exists(FILENAME_UPLOAD)
    create_dir_if_not_exists(FILENAME_SECONDARY_BACKUP)
    init_db(DATABASE)


def create_dir_if_not_exists(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)


def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def init_db(database_name):
    with app.app_context():
        conn = get_db()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users
                    (class TEXT,
                    name TEXT,
                    id TEXT PRIMARY KEY,
                    phone TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS uploads
                    (id TEXT,
                    count INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS second_backup
                    (id TEXT,
                    count INTEGER,
                    filename TEXT,
                    sqltime TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()

init()
if __name__ == "__main__":
    app.run(host='0.0.0.0')
