from flask import Flask
from flask import send_file
from flask import send_from_directory
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
from collections import OrderedDict
from distutils.version import StrictVersion
from datetime import timedelta
from datetime import datetime

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
    return json.dumps({'status': False, 'message': '学号已注册。'})


@app.route('/info', methods=['GET'])
def info():
    student_id = request.args.get('id')
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT `class`,`name`,`id`,`phone` FROM `users` WHERE `id` = %s AND `is_deleted` = 0''', (student_id,))
    out = c.fetchall()
    if out:
        out = out[0]
        out['status'] = True
        return json.dumps(out)
    else:
        return json.dumps({'status': False, 'message': '用户名不存在'})


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
    file_ext = '.' + orig_filename.split(os.extsep, 1)[-1]
    # file_ext = os.path.splitext(orig_filename)[1]

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


@app.route('/checkUpdate', methods=['GET', 'POST'])
def check_update():
    if request.method == 'GET':
        student_id = request.args.get('id')
        student_version = request.args.get('version')
        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT INTO `user_versions` (id, version) VALUES (%s, %s)", (student_id, student_version))
        conn.commit()
        c.execute("SELECT `value` FROM `meta` WHERE `name` = %s", 'version')
        app_version = c.fetchone()
        if app_version:
            app_version = app_version['value']
        c.execute("SELECT `value` FROM `meta` WHERE `name` = %s", 'url')
        app_url = c.fetchone()
        if app_url:
            app_url = app_url['value']
        if app_version and app_url:
            if StrictVersion(student_version) < StrictVersion(app_version):
                return json.dumps(
                    {'status': True, 'has_update': True, 'latest_version': app_version, 'latest_url': app_url})
            else:
                return json.dumps({'status': True, 'has_update': False})
        return json.dumps({'status': False})
    if request.method == 'POST':
        app_version = request.form['version']
        app_url = request.form['url']
        if app_version and app_url:
            conn = get_db()
            c = conn.cursor()
            c.execute("REPLACE INTO `meta` (`name`,`value`) VALUES (%s, %s)", ('version', app_version))
            c.execute("REPLACE INTO `meta` (`name`,`value`) VALUES (%s, %s)", ('url', app_url))
            conn.commit()
            return json.dumps({'status': True})
        return json.dumps({'status': False})


@app.route('/survey', methods=['GET'])
def survey():
    INTERVAL = timedelta(hours=5)
    student_id = request.args.get('id')
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT upload_time FROM `survey_uploads` WHERE id = %s AND is_uploaded = 1 ORDER BY upload_time DESC LIMIT 1",
        (student_id,))
    last_uplod_time = c.fetchone()
    if last_uplod_time:
        last_uplod_time = last_uplod_time['upload_time']
        next_upload_time = last_uplod_time + INTERVAL
        if datetime.now() < next_upload_time:
            return json.dumps({'status': False, 'message': '您的提交频率太快，下次提交时间为：' + str(next_upload_time) + ' 之后'})
    survey_id = 1
    session = str(uuid.uuid4())
    result = {
        'id': survey_id,
        'session': session,
        'questions': []
    }
    c.execute("INSERT INTO `survey_uploads` (id, survey_id, session) VALUES (%s, %s, %s)",
              (student_id, survey_id, session))
    conn.commit()
    c.execute("SELECT question_id FROM `survey` WHERE id = %s", (survey_id,))
    question_ids = [item['question_id'] for item in c.fetchall()]
    for question_id in question_ids:
        c.execute(
            "SELECT id, type, title, description, choices_id, children_id, has_title, has_description, has_choices, has_children FROM `question` WHERE id = %s",
            (question_id,))
        question = c.fetchone()
        if question:
            if question['has_choices']:
                c.execute(
                    "SELECT b.id AS id,b.description AS description FROM `choices` AS a JOIN `choice` AS b ON a.choice_id = b.id WHERE a.id = %s",
                    (question['choices_id']))
                question['choices'] = c.fetchall()
            if question['has_children']:
                c.execute(
                    "SELECT b.id AS id, b.type AS type, b.title AS title, b.description AS description, b.choices_id AS choices_id, b.children_id AS children_id, b.has_title AS has_title, b.has_description AS has_description, b.has_choices AS has_choices, b.has_children AS has_children FROM `children` AS a JOIN `question` AS b ON a.question_id = b.id WHERE a.id = %s",
                    (question['children_id']))
                child_questions = c.fetchall()
                question['questions'] = []
                for child_question in child_questions:
                    if child_question['has_choices']:
                        c.execute(
                            "SELECT b.id AS id,b.description AS description FROM `choices` AS a JOIN `choice` AS b ON a.choice_id = b.id WHERE a.id = %s",
                            (child_question['choices_id']))
                        child_question['choices'] = c.fetchall()
                    question['questions'].append(child_question)
            result['questions'].append(question)
    return json.dumps({'status': True, 'survey': json.dumps(result)})


@app.route('/feedback', methods=['GET'])
def feedback():
    student_id = request.args.get('id')
    content = request.args.get('feedback')
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO `feedback` (id,feedback) VALUES (%s, %s)", (student_id, content))
    conn.commit()
    return json.dumps({'status': True})


@app.route('/submitSurvey', methods=['POST'])
def submit_survey():
    student_id = request.form['id']
    if not student_id:
        abort(404)
    session = request.form['session']
    answer = request.form['answer']
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT count(*) AS count FROM `survey_uploads` WHERE `session` = %s", (session,))
    count = c.fetchone()['count']
    if count == 0:
        return json.dumps({'status': False, 'message': "非法提交"})
    c.execute("SELECT count(*) AS count FROM `survey_uploads` WHERE session = %s AND is_uploaded = 1", (session,))
    count = c.fetchone()['count']
    if count == 0:
        c.execute("UPDATE `survey_uploads` SET is_uploaded = 1, upload_time = NOW(), answer = %s WHERE session = %s",
                  (answer, session))
        survey_answer = json.loads(answer)
        survey_id = survey_answer['id']
        answers = survey_answer['answers']
        for item in answers:
            question_id = item['question_id']
            answer = None
            if item['answer']:
                answer = item['answer']
            answer_id = None
            if item['id']:
                answer_id = item['id']
            c.execute(
                "INSERT INTO `answers` (session, survey_id, question_id, answer_id,answer) VALUES (%s,%s,%s,%s,%s)",
                (session, survey_id, question_id, answer_id, answer))
        conn.commit()
        return json.dumps({'status': True})
    else:
        return json.dumps({'status': False, 'message': "请勿重复提交"})


@app.route('/surveyCount', methods=['GET'])
def survey_count():
    student_id = request.args.get('id')
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT count(*) AS count FROM `survey_uploads` WHERE id = %s AND is_uploaded = 1", (student_id,))
    count = c.fetchone()['count']
    message = '您当前已提交 {count} 次，目标次数为 30 次。'.format(count=count)
    if count >= 30:
        message = '恭喜您已完成 30 次提交！当前已提交 {count} 次，目标次数为 60 次。'.format(count=count)
    return json.dumps({'status': True, 'count': count, 'max_count': 30, 'message': message,
                       'url': request.url_root + 'surveyStat?id=' + student_id})


@app.route('/surveyStat', methods=['GET'])
def survey_stat():
    student_id = request.args.get('id')
    conn = get_db()
    c = conn.cursor()

    c.execute(
        "SELECT session, upload_time FROM `survey_uploads` WHERE id = %s AND is_uploaded = 1 ORDER BY upload_time",
        (student_id,))
    surveies = c.fetchall()
    surveies_by_day = {}
    for survey in surveies:
        survey_datetime = survey['upload_time']
        session = survey['session']
        c.execute(
            "SELECT question.title, answers.answer FROM `answers` AS answers, `question` AS question WHERE answers.question_id = question.id AND answers.session = %s ORDER BY question.id",
            (session,))
        content = c.fetchall()
        survey_date = survey_datetime.strftime('%Y-%m-%d')
        if survey_date not in surveies_by_day:
            surveies_by_day[survey_date] = []
        surveies_by_day[survey_date].append({
            'time': survey_datetime.strftime('%H:%M:%S'),
            'answers': content
        })
    surveies_by_day = list(OrderedDict(sorted(surveies_by_day.items())).items())
    return render_template('surveies_stat.html', surveies_by_day=surveies_by_day)


@app.route('/apk/<path:filename>', methods=['GET'])
def apk(filename):
    return send_from_directory(directory='apk', filename=filename)


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


@app.route('/crashReport', methods=['POST'])
def crash_report():
    report = request.data.decode('utf-8')
    report_format = json.loads(report)
    android_version = report_format.get('ANDROID_VERSION')
    app_version_name = report_format.get('APP_VERSION_NAME')
    brand = report_format.get('BRAND')
    product = report_format.get('PRODUCT')
    report_id = report_format.get('REPORT_ID')
    crash_date = report_format.get('USER_CRASH_DATE')
    id = None
    if report_format['SHARED_PREFERENCES'] and report_format['SHARED_PREFERENCES']['default'] and \
            report_format['SHARED_PREFERENCES']['default']['id']:
        id = report_format['SHARED_PREFERENCES']['default']['id']
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT IGNORE INTO `crash_reports` (report_id,id,android_version,app_version_name,brand,product,crash_date,report) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (report_id, id, android_version, app_version_name, brand, product, crash_date, report))
    conn.commit()
    return "OK"


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
        c.execute("SET SESSION group_concat_max_len = 1000000")
        c.execute(
            '''
            SELECT
                users.name, users.id, users.phone, heartbeats.latest_heartbeat, heartbeats.recent_heartbeats,
                versions.latest_version, survies.latest_survey, survies.recent_surveies, survies.survey_count,
                uploads.latest_upload, uploads.recent_uploads, uploads.upload_count
            FROM
              `users` AS users
            LEFT JOIN (
                SELECT
                    id, MAX(timestamp) AS latest_heartbeat,
                    SUBSTRING_INDEX(GROUP_CONCAT(timestamp ORDER BY timestamp DESC), ',', 10) AS recent_heartbeats
                FROM
                    `heartbeats`
                GROUP BY id
            ) AS heartbeats
            ON users.id = heartbeats.id
            LEFT JOIN (
                SELECT
                    id,
                    SUBSTRING_INDEX(GROUP_CONCAT(version ORDER BY INET_ATON(SUBSTRING_INDEX(CONCAT(version,'.0.0.0'),'.',4)) DESC),',',1) AS latest_version
                FROM
                    `user_versions`
                GROUP BY id
            ) AS versions
            ON users.id = versions.id
            LEFT JOIN (
                SELECT
                    id, MAX(upload_time) AS latest_survey,
                    SUBSTRING_INDEX(GROUP_CONCAT(upload_time ORDER BY upload_time DESC), ',', 10) AS recent_surveies,
                    COUNT(*) AS survey_count
                FROM
                    `survey_uploads`
                WHERE
                    is_uploaded = 1
                GROUP BY id
            ) AS survies
            ON users.id = survies.id
            LEFT JOIN (
                SELECT
                    id, MAX(timestamp) AS latest_upload,
                    SUBSTRING_INDEX(GROUP_CONCAT(timestamp ORDER BY timestamp DESC), ',', 10) AS recent_uploads,
                    COUNT(*) AS upload_count
                FROM
                    `uploads`
                WHERE
                    is_deleted = 0
                GROUP BY id
            ) AS uploads
            ON users.id = uploads.id
            WHERE
                users.is_deleted = 0
            ORDER BY users.id
            '''
        )
        rows = c.fetchall()
        for row in rows:
            if row['recent_heartbeats']:
                row['recent_heartbeats'] = row['recent_heartbeats'].split(',')
            else:
                row['recent_heartbeats'] = []
            if row['recent_surveies']:
                row['recent_surveies'] = row['recent_surveies'].split(',')
            else:
                row['recent_surveies'] = []
            if row['recent_uploads']:
                row['recent_uploads'] = row['recent_uploads'].split(',')
            else:
                row['recent_uploads'] = []
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
        c.execute(
            '''CREATE TABLE IF NOT EXISTS
            `survey`
            (
            auto_id INT AUTO_INCREMENT,
            id INT,
            question_id INT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (auto_id)
            )
            '''
        )
        c.execute(
            '''CREATE TABLE IF NOT EXISTS
            `question`
            (
            id INT,
            type VARCHAR(20) NOT NULL,
            title VARCHAR(100),
            description VARCHAR(200),
            choices_id INT,
            children_id INT,
            has_title TINYINT(1) DEFAULT 0,
            has_description TINYINT(1) DEFAULT 0,
            has_choices TINYINT(1) DEFAULT 0,
            has_children TINYINT(1) DEFAULT 0,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id)
            )
            '''
        )
        c.execute(
            '''CREATE TABLE IF NOT EXISTS
            `choices`
            (
            auto_id INT AUTO_INCREMENT,
            id INT,
            choice_id INT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (auto_id)
            )
            '''
        )
        c.execute(
            '''CREATE TABLE IF NOT EXISTS
            `children`
            (
            auto_id INT AUTO_INCREMENT,
            id INT,
            question_id INT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (auto_id)
            )
            '''
        )
        c.execute(
            '''CREATE TABLE IF NOT EXISTS
            `choice`
            (
            id INT,
            description VARCHAR(200) NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id)
            )
            '''
        )
        c.execute(
            '''CREATE TABLE IF NOT EXISTS
            `survey_uploads`
            (
            auto_id INT AUTO_INCREMENT,
            id VARCHAR(40) NOT NULL,
            survey_id INT NOT NULL,
            session VARCHAR(50) NOT NULL UNIQUE,
            request_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_uploaded TINYINT(1) DEFAULT 0,
            upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            answer TEXT,
            PRIMARY KEY (auto_id)
            )
            '''
        )
        c.execute(
            '''CREATE TABLE IF NOT EXISTS
            `answers`
            (
            auto_id INT AUTO_INCREMENT,
            session VARCHAR(50) NOT NULL,
            survey_id INT NOT NULL,
            question_id INT NOT NULL,
            answer_id INT,
            answer TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (auto_id)
            )
            '''
        )
        c.execute(
            '''CREATE TABLE IF NOT EXISTS
            `feedback`
            (
            auto_id INT AUTO_INCREMENT,
            id VARCHAR(40) NOT NULL,
            feedback TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (auto_id)
            )
            '''
        )
        c.execute(
            '''CREATE TABLE IF NOT EXISTS
            `user_versions`
            (
            auto_id INT AUTO_INCREMENT,
            id VARCHAR(40) NOT NULL,
            version VARCHAR(10),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (auto_id)
            )
            '''
        )
        c.execute(
            '''CREATE TABLE IF NOT EXISTS
            `crash_reports`
            (
            report_id VARCHAR(50),
            id VARCHAR(40),
            android_version VARCHAR(20),
            app_version_name VARCHAR(20),
            brand VARCHAR(40),
            product  VARCHAR(40),
            crash_date DATETIME,
            report LONGTEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (report_id)
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
