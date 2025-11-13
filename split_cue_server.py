#!/usr/bin/env python3
"""
CUE Splitter HTTP Daemon

A multi-threaded HTTP daemon for processing CUE sheet + audio image file pairs.
Features:
- Recursive search for CUE+image pairs in directory trees
- Parallel processing of multiple pairs within a job
- Multi-threaded job queue for handling concurrent requests
- Automatic audio conversion, track splitting, tagging, and optimization
"""
import os
import sys
import json
import argparse
import tempfile
import shutil
import subprocess
import threading
import queue
import signal
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

# Global task queue
task_queue = queue.Queue()
results = {}
lock = threading.Lock()
shutdown_event = threading.Event()

def run_command(cmd, logfile):
    with open(logfile, "a") as f:
        f.write(f"\n$ {' '.join(cmd)}\n")
        f.flush()
        result = subprocess.run(cmd, stdout=f, stderr=f, check=False)
        f.write(f"[Exit code: {result.returncode}]\n")
        f.flush()
        return result.returncode


def find_album_cover(album_path, log_func):
    """
    Search for album cover image in the album directory and subdirectories.
    Priority:
    1. Images with "front" in the name (case insensitive)
    2. First image without "back", "side", or "inner" in the name
    
    Returns: path to cover image or None
    """
    image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.tif', '.webp')
    
    front_images = []
    other_images = []
    
    # Search in album directory and subdirectories
    for root, dirs, files in os.walk(album_path):
        for file in files:
            if file.lower().endswith(image_extensions):
                file_lower = file.lower()
                file_path = os.path.join(root, file)
                
                # Priority 1: Images with "front" in the name
                if "front" in file_lower:
                    front_images.append(file_path)
                # Skip images with back, side, or inner
                elif not any(word in file_lower for word in ["back", "side", "inner"]):
                    other_images.append(file_path)
    
    # Return first front image if found
    if front_images:
        cover = front_images[0]
        log_func(f"🖼️ Found front cover image: {os.path.relpath(cover, album_path)}")
        return cover
    
    # Otherwise return first other suitable image
    if other_images:
        cover = other_images[0]
        log_func(f"🖼️ Found cover image: {os.path.relpath(cover, album_path)}")
        return cover
    
    log_func("ℹ️ No suitable cover image found")
    return None


def find_cue_image_pairs(root_path):
    """
    Recursively search for CUE + image file pairs in root_path and all subdirectories.
    Returns a list of tuples: [(cue_path, image_path, containing_dir), ...]
    """
    pairs = []
    image_extensions = [".ape", ".flac", ".wav", ".wv"]
    
    for dirpath, dirnames, filenames in os.walk(root_path):
        # Find all CUE files in this directory
        cue_files = [f for f in filenames if f.lower().endswith(".cue")]
        
        for cue_file in cue_files:
            cue_path = os.path.join(dirpath, cue_file)
            base_name = os.path.splitext(cue_file)[0]
            
            # Look for matching image file with same base name
            image_file = None
            for ext in image_extensions:
                candidate = os.path.join(dirpath, base_name + ext)
                if os.path.exists(candidate):
                    image_file = candidate
                    break
            
            if image_file:
                pairs.append((cue_path, image_file, dirpath))
    
    return pairs


def split_and_encode(album_path, no_cleanup=False, output_format="flac", job_id=None, max_parallel_pairs=None):
    logdir = "/tmp/cue_split_logs"
    os.makedirs(logdir, exist_ok=True)
    logfile = os.path.join(logdir, f"{job_id}.log")
    
    # Thread-safe logging with lock
    log_lock = threading.Lock()

    def log(msg):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        formatted_msg = f"[{timestamp}] [{job_id}] {msg}"
        with log_lock:
            print(formatted_msg)
            sys.stdout.flush()
            with open(logfile, "a") as f:
                f.write(formatted_msg + "\n")
                f.flush()

    try:
        log(f"🚀 Starting processing for: {album_path}")
        log(f"📋 Output format: {output_format}, Cleanup: {not no_cleanup}")
        
        # Search recursively for CUE + image pairs
        log(f"🔍 Searching for CUE + image file pairs in {album_path} and subdirectories...")
        pairs = find_cue_image_pairs(album_path)
        
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
            
            result = process_single_pair(cue_path, image_file, working_dir, no_cleanup, output_format, job_id, log, logfile, pair_log_prefix)
            
            if result["status"] != "success":
                log(f"{pair_log_prefix} ❌ Failed to process this pair")
            else:
                log(f"{pair_log_prefix} ✅ Successfully processed this pair")
            
            return idx, result
        
        with ThreadPoolExecutor(max_workers=max_parallel_pairs) as executor:
            # Submit all pair processing tasks
            futures = []
            for idx, (cue_path, image_file, working_dir) in enumerate(pairs, 1):
                future = executor.submit(process_pair_wrapper, idx, cue_path, image_file, working_dir)
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
            return {"status": "error", "message": f"all {len(pairs)} pair(s) failed", "log": logfile, "details": all_results}
        elif failed_count > 0:
            return {"status": "partial", "message": f"{success_count} succeeded, {failed_count} failed", "log": logfile, "details": all_results}
        else:
            log("✅ Job completed successfully!")
            return {"status": "success", "log": logfile, "details": all_results}

    except Exception as e:
        log(f"💥 Fatal error: {str(e)}")
        import traceback
        log(f"Stack trace:\n{traceback.format_exc()}")
        return {"status": "error", "message": str(e), "log": logfile}


def process_single_pair(cue_path, image_file, working_dir, no_cleanup, output_format, job_id, log, logfile, log_prefix=""):
    """
    Process a single CUE + image file pair.
    Returns a result dictionary with status and details.
    """
    try:
        base_name = os.path.splitext(os.path.basename(cue_path))[0]
        wav_path = os.path.join(working_dir, base_name + ".temp.wav")

        log(f"{log_prefix} 🔄 Converting {os.path.basename(image_file)} → {os.path.basename(wav_path)} ...")
        # Use explicit PCM format to ensure shnsplit compatibility (avoid WAVE_FORMAT_EXTENSIBLE)
        exit_code = run_command(["ffmpeg", "-y", "-i", image_file, "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", wav_path], logfile)
        if exit_code != 0:
            error_msg = f"ffmpeg conversion failed with exit code {exit_code}"
            log(f"{log_prefix} ❌ {error_msg}")
            log(f"{log_prefix} 📋 Command: ffmpeg -y -i {image_file} {wav_path}")
            log(f"{log_prefix} 📄 Full log available at: {logfile}")
            return {"status": "error", "message": error_msg, "log": logfile, "command": "ffmpeg"}
        log(f"{log_prefix} ✅ Conversion completed successfully")

        log(f"{log_prefix} ✂️ Splitting {os.path.basename(wav_path)} using CUE sheet...")
        # Prepare output format specification
        output_spec = ""
        if output_format == "flac":
            output_spec = "flac flac -8 -o %f -"
        elif output_format == "mp3":
            output_spec = "cust ext=mp3 ffmpeg -i - -codec:a libmp3lame -b:a 320k %f"
        elif output_format == "aac":
            output_spec = "cust ext=aac ffmpeg -i - -c:a aac -b:a 256k %f"
        
        # Change to working directory so shnsplit creates files in the right place
        original_cwd = os.getcwd()
        try:
            os.chdir(working_dir)
            # Use relative paths since we're now in the working directory
            exit_code = run_command(["shnsplit", "-f", os.path.basename(cue_path), "-O", "never", "-o", output_spec, "-t", "%n. %t", os.path.basename(wav_path)], logfile)
        finally:
            os.chdir(original_cwd)
        
        if exit_code != 0:
            error_msg = f"shnsplit failed with exit code {exit_code}"
            log(f"{log_prefix} ❌ {error_msg}")
            log(f"{log_prefix} 📋 Command: shnsplit -f {cue_path} -o {output_format} {working_dir}/track%02d {wav_path}")
            log(f"{log_prefix} 📄 Full log available at: {logfile}")
            # Clean up temp WAV file before returning
            if os.path.exists(wav_path):
                log(f"{log_prefix} 🗑️ Cleaning up temporary WAV file: {os.path.basename(wav_path)}")
                os.remove(wav_path)
            return {"status": "error", "message": error_msg, "log": logfile, "command": "shnsplit"}
        log(f"{log_prefix} ✅ Splitting completed successfully")

        log(f"{log_prefix} 🎧 Tagging tracks with metadata from CUE...")
        track_files = [os.path.join(working_dir, f) for f in sorted(os.listdir(working_dir)) if f.lower().endswith(f".{output_format}")]
        log(f"{log_prefix} 📊 Found {len(track_files)} track(s) to tag")
        if track_files:
            exit_code = run_command(["cuetag", cue_path] + track_files, logfile)
            if exit_code != 0:
                error_msg = f"cuetag failed with exit code {exit_code}"
                log(f"{log_prefix} ❌ {error_msg}")
                log(f"{log_prefix} 📋 Command: cuetag {cue_path} [track files...]")
                log(f"{log_prefix} 📄 Full log available at: {logfile}")
                # Clean up temp WAV file before returning
                if os.path.exists(wav_path):
                    log(f"{log_prefix} 🗑️ Cleaning up temporary WAV file: {os.path.basename(wav_path)}")
                    os.remove(wav_path)
                return {"status": "error", "message": error_msg, "log": logfile, "command": "cuetag"}
            log(f"{log_prefix} ✅ Tagging completed successfully")

        # Find album cover image
        cover_image = find_album_cover(working_dir, log)
        
        log(f"{log_prefix} 🧠 Optimizing compression and embedding album art...")
        tmpdir = tempfile.mkdtemp()
        log(f"{log_prefix} 📁 Created temporary directory: {tmpdir}")
        
        optimization_count = 0
        skipped_count = 0
        
        for file in os.listdir(working_dir):
            if not file.lower().endswith(f".{output_format}"):
                continue
            src = os.path.join(working_dir, file)
            dst = os.path.join(tmpdir, file)

            cmd = []
            if output_format == "flac":
                result = subprocess.run(["metaflac", "--show-compression-level", src], capture_output=True, text=True)
                if result.returncode == 0 and "level 8" in result.stdout:
                    log(f"{log_prefix}   ✅ {file}: already max compression (level 8)")
                    skipped_count += 1
                    continue
                log(f"{log_prefix}   🔧 Optimizing {file} to compression level 8...")
                if cover_image:
                    cmd = ["ffmpeg", "-y", "-i", src, "-i", cover_image, "-map", "0:0", "-map", "1", "-c:a", "flac", "-compression_level", "8", "-c:v", "copy", "-disposition:v", "attached_pic", "-metadata:s:v", "title=Album cover", "-metadata:s:v", "comment=Cover (front)", dst]
                else:
                    cmd = ["ffmpeg", "-y", "-i", src, "-c:a", "flac", "-compression_level", "8", dst]
            elif output_format == "mp3":
                log(f"{log_prefix}   🔧 Encoding {file} to MP3 320k...")
                if cover_image:
                    cmd = ["ffmpeg", "-y", "-i", src, "-i", cover_image, "-map", "0:0", "-map", "1:0", "-c", "copy", "-id3v2_version", "3", "-metadata:s:v", "title=Album cover", "-metadata:s:v", "comment=Cover (front)", dst]
                else:
                    cmd = ["ffmpeg", "-y", "-i", src, "-codec:a", "libmp3lame", "-b:a", "320k", dst]
            elif output_format == "aac":
                log(f"{log_prefix}   🔧 Encoding {file} to AAC 256k...")
                cmd = ["ffmpeg", "-y", "-i", src, "-c:a", "aac", "-b:a", "256k", dst]

            exit_code = run_command(cmd, logfile)
            if exit_code == 0:
                shutil.move(dst, src)
                optimization_count += 1
                log(f"{log_prefix}   ✅ {file}: optimization complete")
            else:
                error_msg = f"Optimization of {file} failed with exit code {exit_code}"
                log(f"{log_prefix}   ❌ {error_msg}")
                log(f"{log_prefix} 📄 Full log available at: {logfile}")
                # Clean up temporary directory and WAV file before returning
                log(f"{log_prefix} 🗑️ Cleaning up temporary directory: {tmpdir}")
                shutil.rmtree(tmpdir, ignore_errors=True)
                if os.path.exists(wav_path):
                    log(f"{log_prefix} 🗑️ Removing temporary WAV file: {os.path.basename(wav_path)}")
                    os.remove(wav_path)
                return {"status": "error", "message": error_msg, "log": logfile, "command": "ffmpeg-optimize"}

        log(f"{log_prefix} 📊 Optimization summary: {optimization_count} optimized, {skipped_count} skipped")
        
        log(f"{log_prefix} 🗑️ Cleaning up temporary directory: {tmpdir}")
        shutil.rmtree(tmpdir, ignore_errors=True)
        
        log(f"{log_prefix} 🗑️ Removing temporary WAV file: {os.path.basename(wav_path)}")
        os.remove(wav_path)

        if not no_cleanup:
            log(f"{log_prefix} 🧹 Cleaning up source files...")
            log(f"{log_prefix}   🗑️ Removing CUE file: {os.path.basename(cue_path)}")
            os.remove(cue_path)
            if os.path.exists(image_file):
                log(f"{log_prefix}   🗑️ Removing image file: {os.path.basename(image_file)}")
                os.remove(image_file)
            log(f"{log_prefix} ✅ Cleanup completed")
        else:
            log(f"{log_prefix} ℹ️ Skipping cleanup (--no-cleanup flag set)")

        return {"status": "success", "log": logfile}

    except Exception as e:
        log(f"{log_prefix} 💥 Fatal error: {str(e)}")
        import traceback
        log(f"{log_prefix} Stack trace:\n{traceback.format_exc()}")
        return {"status": "error", "message": str(e), "log": logfile}


def worker_thread(args, thread_id):
    print(f"[Worker {thread_id}] Thread started")
    sys.stdout.flush()
    
    while not shutdown_event.is_set():
        try:
            task = task_queue.get(timeout=1)
            if task is None:
                print(f"[Worker {thread_id}] Received shutdown signal")
                sys.stdout.flush()
                break
            
            job_id, path = task
            print(f"[Worker {thread_id}] Processing job {job_id}: {path}")
            sys.stdout.flush()
            
            with lock:
                results[job_id]["status"] = "processing"
            
            result = split_and_encode(path, args.no_cleanup, args.format, job_id, args.pair_threads)
            
            with lock:
                results[job_id].update(result)
            
            print(f"[Worker {thread_id}] Completed job {job_id} with status: {result['status']}")
            sys.stdout.flush()
            
            task_queue.task_done()
        except queue.Empty:
            continue
    
    print(f"[Worker {thread_id}] Thread stopped")
    sys.stdout.flush()


class CueSplitHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        """Override to provide more detailed logging"""
        print(f"[HTTP] {self.address_string()} - {format % args}")
        sys.stdout.flush()
    
    def _json(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_POST(self):
        if self.path == "/process":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                path = data["path"]
            except Exception as e:
                print(f"❌ Invalid request: {e}")
                sys.stdout.flush()
                return self._json({"error": "invalid json"}, 400)

            job_id = str(len(results) + 1)
            results[job_id] = {"status": "queued", "path": path}
            task_queue.put((job_id, path))
            print(f"📥 New job queued: {job_id} for path: {path}")
            sys.stdout.flush()
            return self._json({"job_id": job_id, "status": "queued"})

        self._json({"error": "unknown endpoint"}, 404)

    def do_GET(self):
        if self.path == "/status":
            with lock:
                return self._json(results)
        elif self.path.startswith("/log/"):
            job_id = self.path.split("/")[-1]
            log_path = f"/tmp/cue_split_logs/{job_id}.log"
            if os.path.exists(log_path):
                with open(log_path, "r") as f:
                    self._json({"job_id": job_id, "log": f.read()})
            else:
                self._json({"error": "log not found"}, 404)
        else:
            self._json({"message": "endpoints: /process, /status, /log/<jobid>"}, 200)


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    signal_name = signal.Signals(signum).name
    print(f"\n🛑 Received {signal_name} signal, initiating graceful shutdown...")
    sys.stdout.flush()
    shutdown_event.set()


def main():
    parser = argparse.ArgumentParser(description="CUE Splitter HTTP Daemon")
    parser.add_argument("--port", type=int, default=8080, help="HTTP server port (default: 8080)")
    parser.add_argument("--threads", type=int, default=os.cpu_count(), help="Number of job worker threads (default: CPU count)")
    parser.add_argument("--pair-threads", type=int, default=None, help="Max parallel pair processing within a job (default: auto)")
    parser.add_argument("--format", choices=["flac", "mp3", "aac"], default="flac", help="Output audio format (default: flac)")
    parser.add_argument("--no-cleanup", action="store_true", help="Keep original CUE and image files after processing")
    args = parser.parse_args()

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    print("=" * 60)
    print("🎵 CUE Splitter HTTP Daemon")
    print("=" * 60)
    print(f"📋 Configuration:")
    print(f"   Port: {args.port}")
    print(f"   Job worker threads: {args.threads}")
    print(f"   Pair processing threads: {args.pair_threads if args.pair_threads else 'auto (CPU count)'}")
    print(f"   Output format: {args.format}")
    print(f"   Cleanup enabled: {not args.no_cleanup}")
    print(f"   Log directory: /tmp/cue_split_logs")
    print("=" * 60)
    sys.stdout.flush()

    # Start worker threads
    threads = []
    for i in range(args.threads):
        t = threading.Thread(target=worker_thread, args=(args, i+1), daemon=False)
        t.start()
        threads.append(t)
    
    print(f"✅ Started {args.threads} worker thread(s)")
    sys.stdout.flush()

    server = HTTPServer(("0.0.0.0", args.port), CueSplitHandler)
    server.timeout = 1.0  # Poll every second to check shutdown_event
    
    print(f"🚀 Server listening on 0.0.0.0:{args.port}")
    print("📡 API Endpoints:")
    print("   POST /process    - Submit a new CUE split job")
    print("   GET  /status     - Check status of all jobs")
    print("   GET  /log/<id>   - Retrieve log for specific job")
    print("=" * 60)
    print("🟢 Server is ready to accept requests")
    sys.stdout.flush()

    try:
        while not shutdown_event.is_set():
            server.handle_request()  # Will timeout after 1 second if no request
    except KeyboardInterrupt:
        print("\n🛑 Keyboard interrupt received...")
        sys.stdout.flush()
    finally:
        print("🔄 Shutting down server...")
        sys.stdout.flush()
        server.server_close()
        
        print(f"⏳ Waiting for {args.threads} worker thread(s) to finish...")
        sys.stdout.flush()
        
        # Signal all workers to stop
        for _ in range(args.threads):
            task_queue.put(None)
        
        # Wait for all threads to complete
        for i, thread in enumerate(threads, 1):
            thread.join(timeout=5)
            if thread.is_alive():
                print(f"⚠️ Worker {i} did not stop gracefully")
            else:
                print(f"✅ Worker {i} stopped")
            sys.stdout.flush()
        
        print("👋 Shutdown complete")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
