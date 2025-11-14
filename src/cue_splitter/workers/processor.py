"""Worker thread for processing jobs"""
import queue
import threading

from ..utils.helpers import safe_print
from ..core.job_orchestrator import split_and_encode
from ..api.server import update_result


def worker_thread(task_queue, shutdown_event, args, thread_id):
    """
    Worker thread that processes jobs from the task queue.
    
    Args:
        task_queue: Queue to pull tasks from
        shutdown_event: Threading event for graceful shutdown
        args: Arguments object with processing configuration
        thread_id: Unique identifier for this worker thread
    """
    safe_print(f"[Worker {thread_id}] Thread started")
    
    while not shutdown_event.is_set():
        try:
            task = task_queue.get(timeout=1)
            if task is None:
                safe_print(f"[Worker {thread_id}] Received shutdown signal")
                break
            
            job_id, path = task
            safe_print(f"[Worker {thread_id}] Processing job {job_id}: {path}")
            
            update_result(job_id, {"status": "processing"})
            
            result = split_and_encode(
                path, 
                args.no_cleanup, 
                args.format, 
                job_id, 
                args.pair_threads
            )
            
            update_result(job_id, result)
            
            safe_print(f"[Worker {thread_id}] Completed job {job_id} with status: {result['status']}")
            
            task_queue.task_done()
        except queue.Empty:
            continue
    
    safe_print(f"[Worker {thread_id}] Thread stopped")


def start_workers(task_queue, shutdown_event, args, num_threads):
    """
    Start worker threads.
    
    Args:
        task_queue: Queue for tasks
        shutdown_event: Threading event for graceful shutdown
        args: Arguments object with processing configuration
        num_threads: Number of worker threads to start
        
    Returns:
        List of thread objects
    """
    threads = []
    for i in range(num_threads):
        t = threading.Thread(
            target=worker_thread, 
            args=(task_queue, shutdown_event, args, i+1), 
            daemon=False
        )
        t.start()
        threads.append(t)
    
    safe_print(f"✅ Started {num_threads} worker thread(s)")
    return threads


def stop_workers(task_queue, threads, num_threads):
    """
    Stop all worker threads gracefully.
    
    Args:
        task_queue: Queue to send shutdown signals to
        threads: List of thread objects to stop
        num_threads: Number of threads to stop
    """
    safe_print(f"⏳ Waiting for {num_threads} worker thread(s) to finish...")
    
    # Signal all workers to stop
    for _ in range(num_threads):
        task_queue.put(None)
    
    # Wait for all threads to complete
    for i, thread in enumerate(threads, 1):
        thread.join(timeout=5)
        if thread.is_alive():
            safe_print(f"⚠️ Worker {i} did not stop gracefully")
        else:
            safe_print(f"✅ Worker {i} stopped")
