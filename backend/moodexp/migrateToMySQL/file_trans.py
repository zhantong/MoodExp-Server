import pymysql
import os
import os.path
import shutil

MYSQL_DB_CONFIG = {
    'user': 'root',
    'password': '123456',
    'host': 'localhost',
    'db': 'moodexp',
    'charset': 'utf8',
    'cursorclass': pymysql.cursors.DictCursor
}


def load_mysql_uploads(sql):
    conn = pymysql.connect(**MYSQL_DB_CONFIG)
    c = conn.cursor()
    c.execute(sql)
    result = c.fetchall()
    conn.close()
    return result


def trans_second_backup():
    rows = load_mysql_uploads("SELECT `second_backup_path` FROM `uploads`")
    for row in rows:
        second_backup_path = row['second_backup_path']
        file_name = os.path.basename(second_backup_path)
        file_real_path = os.path.join('second_backup', file_name)

        os.makedirs(os.path.dirname(second_backup_path), exist_ok=True)
        shutil.copyfile(file_real_path, second_backup_path)


def trans_backup():
    sql = "SELECT `backup_path`,`second_backup_path` FROM uploads t1 WHERE t1.timestamp = (SELECT MAX(t2.timestamp) FROM uploads t2 WHERE t2.backup_path=t1.backup_path)"
    rows = load_mysql_uploads(sql)
    for row in rows:
        backup_path = row['backup_path']
        second_backup_path = row['second_backup_path']

        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        shutil.copyfile(second_backup_path, backup_path)


def trans_upload():
    sql = "SELECT `upload_path`,`second_backup_path` FROM uploads t1 WHERE t1.timestamp = (SELECT MAX(t2.timestamp) FROM uploads t2 WHERE t2.upload_path=t1.upload_path)"
    rows = load_mysql_uploads(sql)
    for row in rows:
        upload_path = row['upload_path']
        second_backup_path = row['second_backup_path']

        os.makedirs(os.path.dirname(upload_path), exist_ok=True)
        shutil.copyfile(second_backup_path, upload_path)
if __name__ == '__main__':
    # trans_second_backup()
    # trans_backup()
    # trans_upload()
