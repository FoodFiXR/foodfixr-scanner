# gunicorn.conf.py - Professional Tier Optimization
import os
import multiprocessing

# Bind to the port provided by Render
bind = f"0.0.0.0:{os.environ.get('PORT', 5000)}"

# PROFESSIONAL TIER: Can use multiple workers now!
workers = 2  # Increased from 1 - can handle concurrent requests
worker_class = "sync"
worker_connections = 2000  # Increased from 1000

# RELAXED timeout settings - you have more resources
timeout = 180  # 3 minutes (was 120) - can handle complex OCR
keepalive = 120  # Longer keepalive
max_requests = 200  # Increased from 50 - workers can handle more
max_requests_jitter = 20  # Increased jitter range

# Memory management - less aggressive since you have 4GB
preload_app = True  # Can preload now with more memory
worker_tmp_dir = "/dev/shm"  # Use RAM for temp files

# Process management
worker_rlimit_nofile = 2048  # Higher file descriptor limit
max_worker_connections = 2000

# Graceful shutdowns
graceful_timeout = 45  # More time for cleanup
kill_timeout = 10

# Logging (same as before)
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Professional tier detection and optimization
print("INFO: Professional tier configuration loaded")
print(f"INFO: Using {workers} workers with {timeout}s timeout")
print(f"INFO: Max requests per worker: {max_requests}")

def when_ready(server):
    print(f"INFO: Professional tier server ready - PID: {os.getpid()}")
    print(f"INFO: Workers: {workers}, Memory: ~4GB available")
