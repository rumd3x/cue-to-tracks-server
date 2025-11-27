"""HTTP server implementation"""
import os
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from ..utils.helpers import safe_print
from ..utils.database import get_database


class CueSplitHandler(BaseHTTPRequestHandler):
    """HTTP request handler for CUE splitting operations"""
    
    # Class variable to hold the task queue
    task_queue = None
    
    def log_message(self, format, *args):
        """Override to provide more detailed logging"""
        safe_print(f"[HTTP] {self.address_string()} - {format % args}")
    
    def _json(self, data, code=200):
        """Send JSON response"""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_POST(self):
        """Handle POST requests"""
        if self.path == "/process":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                path = data["path"]
            except Exception as e:
                safe_print(f"❌ Invalid request: {e}")
                return self._json({"error": "invalid json"}, 400)

            db = get_database()
            job_id = db.get_next_job_id()
            db.create_job(job_id, path)
            
            if self.task_queue:
                self.task_queue.put((job_id, path))
            
            safe_print(f"📥 New job queued: {job_id} for path: {path}")
            return self._json({"job_id": job_id, "status": "queued"})

        self._json({"error": "unknown endpoint"}, 404)

    def do_GET(self):
        """Handle GET requests"""
        if self.path == "/status":
            db = get_database()
            all_jobs = db.get_all_jobs()
            return self._json(all_jobs)
        elif self.path.startswith("/status/"):
            job_id = self.path.split("/")[-1]
            db = get_database()
            job = db.get_job(job_id)
            if job:
                self._json({"job_id": job_id, **job})
            else:
                self._json({"error": "job not found"}, 404)
        elif self.path.startswith("/log/"):
            job_id = self.path.split("/")[-1]
            log_path = f"/tmp/cue_split_logs/{job_id}.log"
            if os.path.exists(log_path):
                with open(log_path, "r") as f:
                    self._json({"job_id": job_id, "log": f.read()})
            else:
                self._json({"error": "log not found"}, 404)
        else:
            self._json({"message": "endpoints: /process, /status, /status/<jobid>, /log/<jobid>"}, 200)


def start_server(host, port, task_queue, shutdown_event):
    """
    Start the HTTP server.
    
    Args:
        host: Host address to bind to
        port: Port number to listen on
        task_queue: Queue for submitting processing tasks
        shutdown_event: Threading event for graceful shutdown
        
    Returns:
        HTTPServer instance
    """
    # Set the task queue as a class variable
    CueSplitHandler.task_queue = task_queue
    
    server = HTTPServer((host, port), CueSplitHandler)
    server.timeout = 1.0  # Poll every second to check shutdown_event
    
    safe_print(f"🚀 Server listening on {host}:{port}")
    safe_print("📡 API Endpoints:")
    safe_print("   POST /process       - Submit a new CUE split job")
    safe_print("   GET  /status        - Check status of all jobs")
    safe_print("   GET  /status/<id>   - Check status of specific job")
    safe_print("   GET  /log/<id>      - Retrieve log for specific job")
    safe_print("=" * 60)
    safe_print("🟢 Server is ready to accept requests")

    try:
        while not shutdown_event.is_set():
            server.handle_request()  # Will timeout after 1 second if no request
    except KeyboardInterrupt:
        safe_print("\n🛑 Keyboard interrupt received...")
    finally:
        safe_print("🔄 Shutting down server...")
        server.server_close()
    
    return server


def get_results():
    """Get current job results from database"""
    db = get_database()
    return db.get_all_jobs()


def update_result(job_id, updates):
    """Update job result in database"""
    db = get_database()
    db.update_job(job_id, updates)
