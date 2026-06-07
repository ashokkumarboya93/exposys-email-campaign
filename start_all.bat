@echo off
echo Starting Exposys Email Campaign Services...

echo Starting Redis...
start "Redis Server" cmd /k "cd redis-windows && redis-server.exe"

echo Starting Django API...
start "Django API" cmd /k "venv\Scripts\activate && python manage.py runserver 0.0.0.0:8000"

echo Starting Celery Email Worker...
start "Celery Email" cmd /k "venv\Scripts\activate && celery -A config worker -Q email_sending -P solo --loglevel=info --max-tasks-per-child=10"

echo Starting Celery Bulk Worker...
start "Celery Bulk" cmd /k "venv\Scripts\activate && celery -A config worker -Q file_processing,bulk_ops,celery -P prefork --concurrency=4 --loglevel=info"

echo Starting Celery Beat...
start "Celery Beat" cmd /k "venv\Scripts\activate && celery -A config beat --loglevel=info"

echo All services have been launched in separate windows!
echo You can close those windows to stop the services.
pause
