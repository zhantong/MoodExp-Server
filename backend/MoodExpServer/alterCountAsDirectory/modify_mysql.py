import pymysql
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


def trans_backup_mysql():
    file_ext = '.db'
    conn = pymysql.connect(**MYSQL_DB_CONFIG)
    c = conn.cursor()
    #c.execute("ALTER TABLE `uploads` ADD `auto_id` INT PRIMARY KEY AUTO_INCREMENT FIRST")
    # conn.commit()
    query = "SELECT `auto_id`,`id`,`count`,`version`,`timestamp`,`second_backup_path` FROM `uploads`"
    c.execute(query)
    backups = c.fetchall()
    update = "UPDATE `uploads` SET `backup_path` = %s WHERE `auto_id` = %s"
    for item in backups:
        auto_id = item['auto_id']
        student_id = item['id']
        count = item['count']
        version = item['version']
        timestamp = item['timestamp']
        second_backup_path = item['second_backup_path']
        time_in_ms = str(round(timestamp.timestamp() * 1000))
        backup_path = os.path.join(
            'backup', version, student_id, str(count), time_in_ms + file_ext)
        c.execute(update, (backup_path, auto_id))
    conn.commit()
    conn.close()


def trans_backup_file():
    # shutil.rmtree('backup')
    conn = pymysql.connect(**MYSQL_DB_CONFIG)
    c = conn.cursor()
    query = "SELECT `backup_path`,`second_backup_path` FROM `uploads`"
    c.execute(query)
    backups = c.fetchall()
    for item in backups:
        backup_path = item['backup_path']
        second_backup_path = item['second_backup_path']
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        shutil.copyfile(second_backup_path, backup_path)
    conn.close()
if __name__ == '__main__':
    # trans_backup_mysql()
    # trans_backup_file()
