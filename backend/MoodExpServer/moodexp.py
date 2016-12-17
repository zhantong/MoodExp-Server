from flask import Flask
from flask import send_file
from flask import request
from flask import g
from flask import render_template
from flask import abort
import json
import os
import shutil
import pymysql
import uuid
import configparser
import os.path
import hashlib
import time

app = Flask(__name__)

BACKUP = 'backup'
UPLOAD = 'uploads'
SECONDARY_BACKUP = 'second_backup'
DB_CONFIG_FILE = 'config.ini'
DB_CONFIG = {
    'user': None,
    'password': None,
    'host': 'localhost',
    'db': 'moodexp',
    'charset': 'utf8',
    'cursorclass': pymysql.cursors.DictCursor
}


def current_milli_time():
    return str(round(time.time() * 1000))


@app.route('/download', methods=['GET'])
def download():
    student_id = request.args.get('id')
    count = int(request.args.get('count'))
    app_version = request.args.get('version')

    conn = get_db()
    c = conn.cursor()
    c.execute(
        '''SELECT
        `backup_path`
        FROM
        `uploads`
        WHERE
        `id` = %s AND `count` = %s AND `version` = %s
        ORDER BY
        `timestamp`
        DESC
        LIMIT 1''',
        (student_id, count, app_version))
    out = c.fetchone()
    if out:
        path = out['backup_path']
        return send_file(path)
    else:
        abort(404)


@app.route('/register', methods=['GET'])
def register():
    class_name = request.args.get('class')
    name = request.args.get('name')
    student_id = request.args.get('id')
    phone = request.args.get('phone')

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT count(*) AS count FROM `users` WHERE `id` = %s AND `is_deleted` = 0", (student_id,))
    count = c.fetchone()['count']
    if count == 0:
        c.execute(
            '''REPLACE INTO
            `users`
            (`class`,`name`,`id`,`phone`,`is_deleted`)
            VALUES
            (%s,%s,%s,%s,%s)''',
            (class_name, name, student_id, phone, 0))
        conn.commit()
        return json.dumps({'status': True})
    return json.dumps({'status': False})


@app.route('/info', methods=['GET'])
def info():
    student_id = request.args.get('id')
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT * FROM `users` WHERE `id` = %s AND `is_deleted` = 0''', (student_id,))
    out = c.fetchall()
    if out:
        out = out[0]
        out['status'] = True
        return json.dumps(out)
    else:
        return json.dumps({'status': False})


@app.route('/delete', methods=['GET'])
def delete():
    student_id = request.args.get('id')
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE `users` SET `is_deleted` = 1 WHERE `id` = %s", (student_id,))
    c.execute("UPDATE `uploads` SET `is_deleted` = 1 WHERE `id` = %s", (student_id,))
    conn.commit()
    return json.dumps({'status': True})


@app.route('/upload', methods=['POST'])
def upload():
    f = request.files['file']
    student_id = request.form['id']
    count = int(request.form['count'])
    app_version = request.form['version']
    orig_filename = f.filename
    file_ext = os.path.splitext(orig_filename)[1]

    backup_path = os.path.join(BACKUP, app_version, student_id, str(count), current_milli_time() + file_ext)
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    f.save(backup_path)

    upload_path = os.path.join(UPLOAD, app_version, student_id + file_ext)
    os.makedirs(os.path.dirname(upload_path), exist_ok=True)
    shutil.copyfile(backup_path, upload_path)

    second_backup_path = os.path.join(SECONDARY_BACKUP, app_version, student_id, str(uuid.uuid4()))
    os.makedirs(os.path.dirname(second_backup_path), exist_ok=True)
    shutil.copyfile(backup_path, second_backup_path)

    sha1 = calc_sha1(backup_path)

    conn = get_db()
    c = conn.cursor()
    c.execute(
        '''INSERT INTO
        `uploads`
        (`id`,`count`,`version`,`sha1`,`upload_path`,`backup_path`,`second_backup_path`,`is_deleted`)
        VALUES
        (%s,%s,%s,%s,%s,%s,%s,%s)''',
        (student_id, count, app_version, sha1, upload_path, backup_path, second_backup_path, 0))
    conn.commit()
    return json.dumps({'status': True, 'sha1': sha1})


@app.route('/statistic', methods=['GET'])
def statistic():
    rows = get_statistic()
    return json.dumps(rows)


@app.route('/stat', methods=['GET'])
def stat():
    rows = get_statistic()
    return render_template('stat.html', students=rows)


@app.route('/version', methods=['GET', 'POST'])
def version():
    version_type = None
    if request.method == 'GET':
        version_type = request.args.get('type')
    elif request.method == 'POST':
        version_type = request.form['type']
    if version_type == 'release':
        version_type = 'version_release'
    elif version_type == 'debug':
        version_type = 'version_debug'
    else:
        abort(404)
    if request.method == 'GET':
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT `value` FROM `meta` WHERE `name` = %s", (version_type,))
        app_version = c.fetchone()
        if app_version:
            app_version = app_version['value']
            return json.dumps({'status': True, 'version': app_version})
        return json.dumps({'status': False})
    if request.method == 'POST':
        app_version = request.form['version']
        conn = get_db()
        c = conn.cursor()
        c.execute("REPLACE INTO `meta` (`name`,`value`) VALUES (%s, %s)", (version_type, app_version))
        conn.commit()
        return json.dumps({'status': True})


@app.route('/heartbeat', methods=['GET'])
def heartbeat():
    student_id = request.args.get('id')
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO `heartbeats` (`id`) VALUES (%s)", (student_id,))
    conn.commit()
    return json.dumps({'status': True})


@app.route('/questionnaireurl', methods=['GET', 'POST'])
def questionnaireurl():
    if request.method == 'GET':
        group_id = request.args.get('group')
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT `url` FROM `questionnaire_urls` WHERE `group_id` = %s", (group_id,))
        url = c.fetchone()
        if url:
            url = url['url']
            return json.dumps({'status': True, 'url': url})
        return json.dumps({'status': False})
    if request.method == 'POST':
        group_id = request.form['group']
        url = request.form['url']
        conn = get_db()
        c = conn.cursor()
        c.execute("REPLACE INTO `questionnaire_urls` (`group_id`,`url`) VALUES (%s,%s)", (group_id, url))
        conn.commit()
        return json.dumps({'status': True})


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = pymysql.connect(**DB_CONFIG)
    return db


def get_statistic():
    with app.app_context():
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM `users` WHERE `is_deleted` = 0")
        rows = c.fetchall()
        for row in rows:
            student_id = row['id']
            row['uploads'] = {}
            c.execute(
                '''SELECT
                `count`,`version`
                FROM
                `uploads`
                WHERE
                `id` = %s AND `is_deleted` = 0
                ORDER BY
                `count`
                ASC''',
                (student_id,))
            for item in c.fetchall():
                count = item['count']
                app_version = item['version']
                if app_version not in row['uploads']:
                    row['uploads'][app_version] = []
                row['uploads'][app_version].append(count)
            c.execute(
                '''SELECT
                `timestamp`
                FROM
                `heartbeats`
                WHERE
                `id` = %s
                ORDER BY
                `timestamp`
                DESC LIMIT 10''',
                (student_id,))
            out = c.fetchall()
            row['heartbeats'] = [item['timestamp'].strftime("%m-%d %H:%M:%S") for item in out]
        return rows


def init():
    os.makedirs(BACKUP, exist_ok=True)
    os.makedirs(UPLOAD, exist_ok=True)
    os.makedirs(SECONDARY_BACKUP, exist_ok=True)
    load_db_user_passwd(DB_CONFIG, DB_CONFIG_FILE)
    init_db()


def load_db_user_passwd(dic, config_file_path):
    config = configparser.ConfigParser()
    config.read(config_file_path)
    dic['user'] = config['database']['user']
    dic['password'] = config['database']['password']


def init_db():
    with app.app_context():
        conn = get_db()
        c = conn.cursor()
        c.execute(
            '''CREATE TABLE IF NOT EXISTS
            `users`
            (
            `class` VARCHAR(20),
            `name` VARCHAR(20),
            `id` VARCHAR(40),
            `phone` VARCHAR(20),
            `is_deleted` TINYINT DEFAULT 0,
            PRIMARY KEY (`id`)
            )
            ''')
        c.execute(
            '''CREATE TABLE IF NOT EXISTS
            `uploads`
            (
            `auto_id` INT AUTO_INCREMENT,
            `id` VARCHAR(40),
            `count` INTEGER(4),
            `version` VARCHAR(20),
            `sha1` VARCHAR(60),
            `timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            `upload_path` VARCHAR(200),
            `backup_path` VARCHAR(200),
            `second_backup_path` VARCHAR(200),
            `is_deleted` TINYINT DEFAULT 0,
            PRIMARY KEY (`auto_id`)
            )
            ''')
        c.execute(
            '''CREATE TABLE IF NOT EXISTS
            `meta`
            (
            `name` VARCHAR(40),
            `value` VARCHAR(200),
            `timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`name`)
            )
            ''')
        c.execute(
            '''CREATE TABLE IF NOT EXISTS
            `heartbeats`
            (
            `id` VARCHAR(40),
            `timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
        c.execute(
            '''CREATE TABLE IF NOT EXISTS
            `questionnaire_urls`
            (
            `group_id` VARCHAR(40),
            `url` VARCHAR(512),
            `timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`group_id`)
            )
            '''
        )
        conn.commit()


def calc_sha1(file_path):
    with open(file_path, 'rb') as f:
        content = f.read()
        sha1 = hashlib.sha1(content).hexdigest()
        return sha1


init()
if __name__ == "__main__":
    app.run(host='0.0.0.0')
