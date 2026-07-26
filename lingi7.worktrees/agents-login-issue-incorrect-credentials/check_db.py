from django.db import connection

cursor = connection.cursor()

cursor.execute(
    "SELECT column_name FROM information_schema.columns "
    "WHERE table_name='users_user' ORDER BY ordinal_position"
)
print("COLUMNS:", [r[0] for r in cursor.fetchall()])

cursor.execute(
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_name IN ('auth_user', 'users_user')"
)
print("TABLES:", [r[0] for r in cursor.fetchall()])
