# gunicorn.conf.py - Production configuration for FoodFixr Scanner
import os
import multiprocessing

# Bind to the port provided by Render
bind = f"0.0.0.0:{os.environ.get('PORT', 5000)}"

# Worker settings for memory-constrained environment
workers = 1  # Single worker to avoid memory issues on free tier
worker_class = "sync"
worker_connections = 1000

# CRITICAL: Timeout settings to prevent 502 errors
timeout = 120  # Increased from default 30 seconds for OCR processing
keepalive = 60  # Keep connections alive
max_requests = 50  # Restart workers after 50 requests to prevent memory leaks
max_requests_jitter = 10  # Add randomness to worker restarts

# Memory management settings
preload_app = False  # Don't preload to save memory
worker_tmp_dir = "/dev/shm"  # Use RAM for temp files if available

# Process management
worker_rlimit_nofile = 1024  # File descriptor limit
max_worker_connections = 1000

# Graceful shutdowns to prevent data loss
graceful_timeout = 30  # Time to wait for workers to finish
kill_timeout = 5  # Time to wait before forcefully killing workers

# Logging configuration
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Security settings
limit_request_line = 4094  # Max HTTP request line size
limit_request_fields = 100  # Max number of HTTP headers
limit_request_field_size = 8190  # Max size of HTTP header

# SSL settings (if needed)
# keyfile = None
# certfile = None

# Advanced settings for stability
worker_abort_on_timeout = True  # Abort workers that timeout
reuse_port = True  # Enable port reuse for faster restarts

# Environment-specific overrides
if os.environ.get('RENDER'):
    # Render-specific optimizations
    print("INFO: Render environment detected - applying optimizations")
    
    # More conservative settings for Render's free tier
    timeout = 90  # Slightly lower timeout for free tier
    max_requests = 30  # More frequent worker restarts
    
    # Use environment variables if set
    if os.environ.get('WEB_CONCURRENCY'):
        workers = int(os.environ.get('WEB_CONCURRENCY'))
    
    if os.environ.get('TIMEOUT'):
        timeout = int(os.environ.get('TIMEOUT'))

# Logging function for debugging
def when_ready(server):
    """Called when the server is ready to serve requests"""
    print(f"INFO: Gunicorn server ready - PID: {os.getpid()}")
    print(f"INFO: Workers: {workers}, Timeout: {timeout}s")
    print(f"INFO: Listening on {bind}")

def worker_start(server, worker):
    """Called when a worker starts"""
    print(f"INFO: Worker {worker.pid} started")

def worker_exit(server, worker):
    """Called when a worker exits"""
    print(f"INFO: Worker {worker.pid} exited")

def worker_abort(worker):
    """Called when a worker is aborted"""
    print(f"WARNING: Worker {worker.pid} aborted - likely due to timeout or memory issues")

# Error handling
def on_exit(server):
    """Called when the server exits"""
    print("INFO: Gunicorn server shutting down")

def on_reload(server):
    """Called when the server reloads"""
    print("INFO: Gunicorn server reloading")

# Custom application loading
def post_fork(server, worker):
    """Called after worker fork"""
    # Set process title
    try:
        import setproctitle
        setproctitle.setproctitle(f"foodfixr-worker-{worker.pid}")
    except ImportError:
        pass
    
    # Configure garbage collection for worker processes
    import gc
    gc.set_threshold(700, 10, 10)  # Aggressive GC settings
    
    print(f"DEBUG: Worker {worker.pid} post-fork setup complete")

# Pre-application loading
def pre_fork(server, worker):
    """Called before worker fork"""
    print(f"DEBUG: Pre-fork setup for worker {worker.pid}")

# Application-specific settings
pythonpath = "."  # Add current directory to Python path
chdir = "."  # Change to this directory before loading app

# Development vs Production detection
if os.environ.get('FLASK_ENV') == 'development':
    reload = True  # Auto-reload on code changes
    loglevel = "debug"
    print("WARNING: Development mode enabled - auto-reload active")
else:
    reload = False
    print("INFO: Production mode - no auto-reload")

print(f"INFO: Gunicorn configuration loaded")
print(f"INFO: Target bind address: {bind}")
print(f"INFO: Worker configuration: {workers} workers, {timeout}s timeout")
print(f"INFO: Memory management: max_requests={max_requests}, preload_app={preload_app}")
