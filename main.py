#!/usr/bin/env python3
"""
CUE Splitter HTTP Daemon - Main Entry Point

A multi-threaded HTTP daemon for processing CUE sheet + audio image file pairs.
Features:
- Recursive search for CUE+image pairs in directory trees
- Parallel processing of multiple pairs within a job
- Multi-threaded job queue for handling concurrent requests
- Automatic audio conversion, track splitting, tagging, and optimization
"""
import os
import sys
import argparse
import signal
import queue
import threading

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from cue_splitter.utils.helpers import safe_print
from cue_splitter.utils.database import get_database
from cue_splitter.api.server import start_server
from cue_splitter.workers.processor import start_workers, stop_workers


# Global state
task_queue = queue.Queue()
shutdown_event = threading.Event()


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    signal_name = signal.Signals(signum).name
    safe_print(f"\n🛑 Received {signal_name} signal, initiating graceful shutdown...")
    shutdown_event.set()


def parse_arguments():
    """Parse command line arguments and environment variables"""
    # Read defaults from environment variables
    env_threads = int(os.environ.get("THREADS", str(os.cpu_count())))
    env_pair_threads = int(os.environ.get("PAIR_THREADS", str(os.cpu_count())))
    env_format = os.environ.get("FORMAT", "flac")
    env_no_cleanup = os.environ.get("NO_CLEANUP", "false").lower() in ("true", "1", "yes")
    
    parser = argparse.ArgumentParser(
        description="CUE Splitter HTTP Daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --port 8080 --threads 4
  %(prog)s --format mp3 --no-cleanup
  
Environment Variables:
  THREADS       - Number of job worker threads
  PAIR_THREADS  - Max parallel pair processing within a job
  FORMAT        - Output audio format (flac, mp3, aac)
  NO_CLEANUP    - Keep original files (true/false)
"""
    )
    
    parser.add_argument(
        "--port", 
        type=int, 
        default=8080, 
        help="HTTP server port (default: 8080)"
    )
    parser.add_argument(
        "--threads", 
        type=int, 
        default=env_threads, 
        help=f"Number of job worker threads (default: {env_threads}, env: THREADS)"
    )
    parser.add_argument(
        "--pair-threads", 
        type=int, 
        default=env_pair_threads, 
        help="Max parallel pair processing within a job (default: auto, env: PAIR_THREADS)"
    )
    parser.add_argument(
        "--format", 
        choices=["flac", "mp3", "aac"], 
        default=env_format, 
        help=f"Output audio format (default: {env_format}, env: FORMAT)"
    )
    parser.add_argument(
        "--no-cleanup", 
        action="store_true", 
        default=env_no_cleanup, 
        help=f"Keep original CUE and image files after processing (default: {env_no_cleanup}, env: NO_CLEANUP)"
    )
    
    return parser.parse_args()


def print_banner(args, db_path):
    """Print startup banner with configuration"""
    safe_print("=" * 60)
    safe_print("🎵 CUE Splitter HTTP Daemon")
    safe_print("=" * 60)
    safe_print(f"📋 Configuration:")
    safe_print(f"   Port: {args.port}")
    safe_print(f"   Job worker threads: {args.threads}")
    safe_print(f"   Pair processing threads: {args.pair_threads}")
    safe_print(f"   Output format: {args.format}")
    safe_print(f"   Cleanup enabled: {not args.no_cleanup}")
    safe_print(f"   Log directory: /tmp/cue_split_logs")
    safe_print(f"   Database: {db_path}")
    safe_print("=" * 60)


def main():
    """Main entry point"""
    # Parse arguments
    args = parse_arguments()
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Initialize database
    db_path = os.environ.get('CUE_SPLITTER_DB', '/tmp/cue_splitter_jobs.db')
    db = get_database(db_path)
    safe_print(f"💾 Database initialized at: {db_path}")
    
    # Print banner
    print_banner(args, db_path)
    
    # Start worker threads
    threads = start_workers(task_queue, shutdown_event, args, args.threads)
    
    # Start HTTP server (blocking)
    try:
        start_server("0.0.0.0", args.port, task_queue, shutdown_event)
    finally:
        # Stop workers
        stop_workers(task_queue, threads, args.threads)
        safe_print("👋 Shutdown complete")


if __name__ == "__main__":
    main()
