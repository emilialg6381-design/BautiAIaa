# gunicorn.conf.py — Optimized for BautiAI NEXUS
import multiprocessing
import os

# ═══════════════════════════════════════════════
# WORKERS — Solo 1 para compartir jobs dict
# ═══════════════════════════════════════════════
workers = 1

# ═══════════════════════════════════════════════
# THREADS — Concurrencia para requests web
# ═══════════════════════════════════════════════
threads = 8

# ═══════════════════════════════════════════════
# WORKER CLASS — gthread = threaded sync worker
# ═══════════════════════════════════════════════
worker_class = "gthread"

# ═══════════════════════════════════════════════
# TIMEOUT — Sin timeout para procesos largos
# ═══════════════════════════════════════════════
timeout = 0

# ═══════════════════════════════════════════════
# GRACEFUL TIMEOUT
# ═══════════════════════════════════════════════
graceful_timeout = 10

# ═══════════════════════════════════════════════
# BIND — Puerto y host
# ═══════════════════════════════════════════════
bind = "0.0.0.0:5000"

# ═══════════════════════════════════════════════
# PRELOAD — Carga código una vez
# ═══════════════════════════════════════════════
preload_app = True

# ═══════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════
accesslog = "-"
errorlog = "-"
loglevel = "info"

# ═══════════════════════════════════════════════
# PROC NAME
# ═══════════════════════════════════════════════
proc_name = "bautiai-nexus"

# ═══════════════════════════════════════════════
# MAX REQUESTS — Reiniciar worker periódicamente
# ═══════════════════════════════════════════════
max_requests = 500
max_requests_jitter = 50

# ═══════════════════════════════════════════════
# DAEMON
# ═══════════════════════════════════════════════
daemon = False

# ═══════════════════════════════════════════════
# PID FILE
# ═══════════════════════════════════════════════
pidfile = "gunicorn.pid"

def post_fork(server, worker):
    """After worker fork"""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def when_ready(server):
    """When Gunicorn is ready"""
    server.log.info("🎬 BautiAI NEXUS listo — http://0.0.0.0:5000")
    server.log.info("Workers: %d | Threads: %d | Timeout: %s", workers, threads, timeout)

def worker_int(worker):
    """Worker received INT signal"""
    worker.log.info("Worker recibió INT signal")
