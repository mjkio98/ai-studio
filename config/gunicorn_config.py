# Gunicorn Configuration for YouTube Summarizer
# Run with: gunicorn -c gunicorn_config.py app:app

import multiprocessing
import os

# Server socket
bind = "0.0.0.0:5001"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1  # Optimal worker count
worker_class = "sync"
worker_connections = 1000
timeout = 120  # Increased timeout for AI processing
keepalive = 2

# Restart workers after this many requests, to prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Logging
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
loglevel = "info"

# Process naming
proc_name = 'youtube-summarizer'

# Worker timeout for graceful shutdown
graceful_timeout = 30

# Preload application for better performance
preload_app = True

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Performance tuning
worker_tmp_dir = "/dev/shm" if os.path.exists("/dev/shm") else None

def when_ready(server):
    server.log.info("🚀 YouTube Summarizer is ready to handle concurrent requests!")
    server.log.info(f"👥 Running with {workers} workers for optimal performance")
    server.log.info("🌐 Access at: http://0.0.0.0:5001")

def worker_int(worker):
    worker.log.info("🔄 Worker received INT or QUIT signal")

def pre_fork(server, worker):
    server.log.info(f"👤 Worker {worker.pid} spawned")

def post_fork(server, worker):
    server.log.info(f"✅ Worker {worker.pid} ready to serve requests")