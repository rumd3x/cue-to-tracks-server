"""SQLite database for persistent job storage"""
import sqlite3
import json
import threading
import os
from contextlib import contextmanager


class JobDatabase:
    """Thread-safe SQLite database for job persistence"""
    
    def __init__(self, db_path="/tmp/cue_splitter_jobs.db"):
        """
        Initialize the database connection.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self.local = threading.local()
        self._init_db()
    
    def _get_connection(self):
        """Get a thread-local database connection"""
        if not hasattr(self.local, 'connection'):
            self.local.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0
            )
            self.local.connection.row_factory = sqlite3.Row
        return self.local.connection
    
    @contextmanager
    def _get_cursor(self):
        """Context manager for database operations"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    
    def _init_db(self):
        """Initialize database schema"""
        with self._get_cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    path TEXT NOT NULL,
                    message TEXT,
                    log TEXT,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create index for faster status queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_status 
                ON jobs(status)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_created_at 
                ON jobs(created_at DESC)
            """)
    
    def create_job(self, job_id, path):
        """
        Create a new job entry.
        
        Args:
            job_id: Unique job identifier
            path: Path to process
            
        Returns:
            Dictionary with job information
        """
        with self._get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO jobs (job_id, status, path)
                VALUES (?, ?, ?)
            """, (job_id, "queued", path))
        
        return {"job_id": job_id, "status": "queued", "path": path}
    
    def get_job(self, job_id):
        """
        Get a specific job by ID.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Dictionary with job information or None if not found
        """
        with self._get_cursor() as cursor:
            cursor.execute("""
                SELECT job_id, status, path, message, log, details
                FROM jobs
                WHERE job_id = ?
            """, (job_id,))
            
            row = cursor.fetchone()
            if row:
                job = dict(row)
                # Parse JSON details if present
                if job.get('details'):
                    try:
                        job['details'] = json.loads(job['details'])
                    except json.JSONDecodeError:
                        pass
                return job
            return None
    
    def get_all_jobs(self):
        """
        Get all jobs.
        
        Returns:
            Dictionary mapping job_id to job information
        """
        with self._get_cursor() as cursor:
            cursor.execute("""
                SELECT job_id, status, path, message, log, details
                FROM jobs
                ORDER BY created_at DESC
            """)
            
            jobs = {}
            for row in cursor.fetchall():
                job = dict(row)
                job_id = job.pop('job_id')
                
                # Parse JSON details if present
                if job.get('details'):
                    try:
                        job['details'] = json.loads(job['details'])
                    except json.JSONDecodeError:
                        pass
                
                jobs[job_id] = job
            
            return jobs
    
    def update_job(self, job_id, updates):
        """
        Update a job's information.
        
        Args:
            job_id: Job identifier
            updates: Dictionary of fields to update
            
        Returns:
            True if job was found and updated, False otherwise
        """
        # Build dynamic UPDATE statement based on provided fields
        allowed_fields = {'status', 'message', 'log', 'details'}
        update_fields = {k: v for k, v in updates.items() if k in allowed_fields}
        
        if not update_fields:
            return True  # No valid fields to update
        
        # Serialize details to JSON if present
        if 'details' in update_fields:
            update_fields['details'] = json.dumps(update_fields['details'])
        
        set_clause = ", ".join(f"{field} = ?" for field in update_fields)
        values = list(update_fields.values())
        values.append(job_id)
        
        with self._get_cursor() as cursor:
            cursor.execute(f"""
                UPDATE jobs
                SET {set_clause}, updated_at = CURRENT_TIMESTAMP
                WHERE job_id = ?
            """, values)
            
            return cursor.rowcount > 0
    
    def get_next_job_id(self):
        """
        Get the next job ID (sequential).
        
        Returns:
            Next job ID as string
        """
        with self._get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM jobs")
            row = cursor.fetchone()
            return str(row['count'] + 1)
    
    def cleanup_old_jobs(self, days=30):
        """
        Delete jobs older than specified days.
        
        Args:
            days: Number of days to keep jobs
            
        Returns:
            Number of deleted jobs
        """
        with self._get_cursor() as cursor:
            cursor.execute("""
                DELETE FROM jobs
                WHERE created_at < datetime('now', '-' || ? || ' days')
            """, (days,))
            
            return cursor.rowcount
    
    def close(self):
        """Close the database connection"""
        if hasattr(self.local, 'connection'):
            self.local.connection.close()
            delattr(self.local, 'connection')


# Global database instance
_db_instance = None
_db_lock = threading.Lock()


def get_database(db_path=None):
    """
    Get the global database instance (singleton).
    
    Args:
        db_path: Path to database file (only used on first call)
        
    Returns:
        JobDatabase instance
    """
    global _db_instance
    
    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                if db_path is None:
                    db_path = os.environ.get('CUE_SPLITTER_DB', '/tmp/cue_splitter_jobs.db')
                _db_instance = JobDatabase(db_path)
    
    return _db_instance
