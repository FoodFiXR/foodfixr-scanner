# gunicorn.conf.py
import os

# Bind to the port provided by Render
bind = f"0.0.0.0:{os.environ.get('PORT', 5000)}"

# Worker settings for memory-constrained environment
workers = 1  # Single worker to avoid memory issues
worker_class = "sync"
worker_connections = 1000

# Critical timeout settings to prevent 502 errors
timeout = 120  # Increased from default 30 seconds
keepalive = 60
max_requests = 100
max_requests_jitter = 10

# Memory management
preload_app = False  # Don't preload to save memory
worker_tmp_dir = "/dev/shm"  # Use RAM for temp files if available

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Graceful shutdowns
graceful_timeout = 30