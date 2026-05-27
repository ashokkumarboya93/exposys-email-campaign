import pymysql

try:
    conn = pymysql.connect(
        host='127.0.0.1',
        user='exposys_user',
        password='StrongPassword123!',
        database='exposys_db',
        port=3306
    )
    print("Success with 127.0.0.1")
    conn.close()
except Exception as e:
    print(f"Failed with 127.0.0.1: {e}")

try:
    conn = pymysql.connect(
        host='localhost',
        user='exposys_user',
        password='StrongPassword123!',
        database='exposys_db',
        port=3306
    )
    print("Success with localhost")
    conn.close()
except Exception as e:
    print(f"Failed with localhost: {e}")

try:
    conn = pymysql.connect(
        host='localhost',
        user='root',
        password='',
        database='exposys_db',
        port=3306
    )
    print("Success with root (no pass)")
    conn.close()
except Exception as e:
    print(f"Failed with root (no pass): {e}")
