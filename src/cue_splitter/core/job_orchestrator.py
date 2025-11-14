"""Job orchestration and parallel processing"""
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from .file_finder import find_cue_image_pairs
from .audio_processor import process_single_pair


def split_and_encode(album_path, no_cleanup=False, output_format="flac", 
                    job_id=None, max_parallel_pairs=None):
    """
    Main orchestration function for processing all CUE+image pairs in a directory tree.
    
    Args:
        album_path: Root directory to search for CUE+image pairs
        no_cleanup: If True, keep original files after processing
        output_format: Output audio format ('flac', 'mp3', 'aac')
        job_id: Unique identifier for this job
        max_parallel_pairs: Maximum number of pairs to process in parallel (None = auto)
        
    Returns:
        Dictionary with overall status and details
    """
    logdir = "/tmp/cue_split_logs"
    os.makedirs(logdir, exist_ok=True)
    logfile = os.path.join(logdir, f"{job_id}.log")
    
    # Thread-safe logging with lock
    log_lock = threading.Lock()

    def log(msg):
        from ..utils.helpers import safe_print
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        formatted_msg = f"[{timestamp}] [{job_id}] {msg}"
        with log_lock:
            # Use safe_print to handle surrogate characters
            safe_print(formatted_msg)
            with open(logfile, "a", encoding="utf-8", errors="replace") as f:
                f.write(formatted_msg + "\n")
                f.flush()

    try:
        log(f"🚀 Starting processing for: {album_path}")
        log(f"📋 Output format: {output_format}, Cleanup: {not no_cleanup}")
        
        # Search recursively for CUE + image pairs
        log(f"🔍 Searching for CUE + image file pairs in {album_path} and subdirectories...")
        pairs = find_cue_image_pairs(album_path, log_func=log)
        
        if not pairs:
            log("❌ No CUE + image file pairs found.")
            return {"status": "error", "message": "no cue+image pairs found"}
        
        log(f"✅ Found {len(pairs)} CUE + image file pair(s)")
        
        # Determine number of parallel workers
        if max_parallel_pairs is None:
            max_parallel_pairs = min(len(pairs), os.cpu_count() or 1)
        
        if len(pairs) == 1:
            log(f"🔧 Processing single pair sequentially")
            max_parallel_pairs = 1
        else:
            log(f"🔧 Processing pairs with {max_parallel_pairs} parallel worker(s)")
        
        # Process pairs in parallel using ThreadPoolExecutor
        all_results = [None] * len(pairs)  # Pre-allocate to maintain order
        
        def process_pair_wrapper(idx, cue_path, image_file, working_dir):
            pair_log_prefix = f"[Pair {idx}/{len(pairs)}]"
            log(f"{pair_log_prefix} Processing pair in: {os.path.relpath(working_dir, album_path)}")
            log(f"{pair_log_prefix} 📄 CUE file: {os.path.basename(cue_path)}")
            log(f"{pair_log_prefix} 🎵 Image file: {os.path.basename(image_file)}")
            
            result = process_single_pair(
                cue_path, image_file, working_dir, no_cleanup, 
                output_format, job_id, log, logfile, pair_log_prefix
            )
            
            if result["status"] != "success":
                log(f"{pair_log_prefix} ❌ Failed to process this pair")
            else:
                log(f"{pair_log_prefix} ✅ Successfully processed this pair")
            
            return idx, result
        
        with ThreadPoolExecutor(max_workers=max_parallel_pairs) as executor:
            # Submit all pair processing tasks
            futures = []
            for idx, (cue_path, image_file, working_dir) in enumerate(pairs, 1):
                future = executor.submit(
                    process_pair_wrapper, idx, cue_path, image_file, working_dir
                )
                futures.append(future)
            
            # Collect results as they complete
            for future in as_completed(futures):
                try:
                    idx, result = future.result()
                    all_results[idx - 1] = result
                except Exception as e:
                    log(f"💥 Exception in pair processing thread: {str(e)}")
                    import traceback
                    log(f"Stack trace:\n{traceback.format_exc()}")
        
        # Check overall status
        failed_count = sum(1 for r in all_results if r and r["status"] != "success")
        success_count = sum(1 for r in all_results if r and r["status"] == "success")
        
        log(f"📊 Overall summary: {success_count} successful, {failed_count} failed out of {len(pairs)} pair(s)")
        
        if failed_count == len(all_results):
            return {
                "status": "error", 
                "message": f"all {len(pairs)} pair(s) failed", 
                "log": logfile, 
                "details": all_results
            }
        elif failed_count > 0:
            return {
                "status": "partial", 
                "message": f"{success_count} succeeded, {failed_count} failed", 
                "log": logfile, 
                "details": all_results
            }
        else:
            log("✅ Job completed successfully!")
            return {"status": "success", "log": logfile, "details": all_results}

    except Exception as e:
        log(f"💥 Fatal error: {str(e)}")
        import traceback
        log(f"Stack trace:\n{traceback.format_exc()}")
        return {"status": "error", "message": str(e), "log": logfile}
