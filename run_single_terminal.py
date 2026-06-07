import subprocess
import sys
import time
import os

def main():
    print("Starting all Exposys Email Campaign Services...")
    print("This will run all services in this single terminal window.")
    print("Press Ctrl+C at any time to stop all of them gracefully.\n")
    
    # Path to virtual environment python/celery
    venv_python = os.path.join("venv", "Scripts", "python.exe")
    venv_celery = os.path.join("venv", "Scripts", "celery.exe")
    
    # Define the commands based on the RUNBOOK
    commands = [
        {"name": "Redis", "cmd": [os.path.join("redis-windows", "redis-server.exe")]},
        {"name": "Django API", "cmd": [venv_python, "manage.py", "runserver", "0.0.0.0:8000"]},
        {"name": "Celery Email", "cmd": [venv_celery, "-A", "config", "worker", "-Q", "email_sending", "-P", "solo", "--loglevel=info", "--max-tasks-per-child=10"]},
        {"name": "Celery Bulk", "cmd": [venv_celery, "-A", "config", "worker", "-Q", "file_processing,bulk_ops,celery", "-P", "prefork", "--concurrency=4", "--loglevel=info"]},
        {"name": "Celery Beat", "cmd": [venv_celery, "-A", "config", "beat", "--loglevel=info"]},
    ]
    
    processes = []
    
    try:
        for item in commands:
            print(f"[{item['name']}] Starting...")
            p = subprocess.Popen(item['cmd'])
            processes.append((item['name'], p))
            time.sleep(2) # Give it a bit of time to start before launching the next
        
        print("\n=======================================================")
        print(" All services are running in this terminal!")
        print(" Press Ctrl+C to stop all services.")
        print("=======================================================\n")
        
        # Wait indefinitely for processes
        for _, p in processes:
            p.wait()
            
    except KeyboardInterrupt:
        print("\n=======================================================")
        print("Shutting down all services...")
        for name, p in processes:
            print(f"Terminating {name}...")
            try:
                p.terminate()
            except Exception:
                pass
        print("All services stopped.")

if __name__ == "__main__":
    main()
