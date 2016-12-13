import sqlite3
import pymysql
import os
import os.path
import hashlib

SQLITE_DB = 'moodexp.db'

MYSQL_DB_CONFIG = {
    'user': 'root',
    'password': '123456',
    'host': 'localhost',
    'db': 'moodexp',
    'charset': 'utf8',
    'cursorclass': pymysql.cursors.DictCursor
}


def load_sqlite_users():
    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = dict_factory
    c = conn.cursor()
    c.execute("SELECT * FROM users")
    users = c.fetchall()
    conn.close()
    return users


def load_sqlite_second_backup():
    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = dict_factory
    c = conn.cursor()
    c.execute("SELECT * FROM second_backup")
    second_backup = c.fetchall()
    conn.close()
    return second_backup


def write_mysql_users(users):
    conn = pymysql.connect(**MYSQL_DB_CONFIG)
    c = conn.cursor()
    sql = "INSERT INTO users (`class`,`name`,`id`,`phone`,`is_deleted`) VALUES (%s,%s,%s,%s,%s)"
    for user in users:
        c.execute(sql, (user['class'], user['name'],
                        user['id'], user['phone'], 0))
    conn.commit()
    conn.close()


def write_mysql_uploads(second_backup):
    conn = pymysql.connect(**MYSQL_DB_CONFIG)
    c = conn.cursor()
    sql = "INSERT INTO uploads (`id`,`count`,`version`,`sha1`,`timestamp`,`upload_path`,`backup_path`,`second_backup_path`,`is_deleted`) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
    version = '1.0'
    file_ext = '.db'
    is_deleted = 0
    for upload in second_backup:
        file_name = upload['filename']
        student_id = upload['id']
        count = upload['count']
        timestamp = upload['sqltime']

        real_path = os.path.join('second_backup', upload['filename'])
        sha1 = calc_sha1(real_path)

        upload_path = os.path.join('uploads', version, student_id + file_ext)
        backup_path = os.path.join(
            'backup', version, student_id, str(count) + file_ext)
        second_backup_path = os.path.join(
            'second_backup', version, student_id, file_name)

        c.execute(sql, (student_id, count, version, sha1, timestamp,
                        upload_path, backup_path, second_backup_path, is_deleted))
    conn.commit()
    conn.close()


def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def calc_sha1(file_path):
    with open(file_path, 'rb') as f:
        content = f.read()
        sha1 = hashlib.sha1(content).hexdigest()
        return sha1
if __name__ == '__main__':
    #users = load_sqlite_users()
    # write_mysql_users(users)

    #second_backup = load_sqlite_second_backup()
    # write_mysql_uploads(second_backup)
