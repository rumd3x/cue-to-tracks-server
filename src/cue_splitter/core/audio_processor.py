"""Audio processing logic for individual CUE+image pairs"""
import os
import tempfile
import shutil
import subprocess

from ..utils.helpers import run_command
from ..utils.encoding import ensure_utf8_cue
from .file_finder import find_album_cover


def process_single_pair(cue_path, image_file, working_dir, no_cleanup, output_format, 
                       job_id, log, logfile, log_prefix=""):
    """
    Process a single CUE + image file pair.
    
    Args:
        cue_path: Path to the CUE sheet file
        image_file: Path to the audio image file (FLAC, APE, WAV, etc.)
        working_dir: Directory where the pair is located
        no_cleanup: If True, keep original files after processing
        output_format: Output audio format ('flac', 'mp3', 'aac')
        job_id: Unique identifier for this job
        log: Function to call for logging messages
        logfile: Path to the log file
        log_prefix: Prefix for log messages
        
    Returns:
        Dictionary with status and details
    """
    try:
        base_name = os.path.splitext(os.path.basename(cue_path))[0]
        wav_path = os.path.join(working_dir, base_name + ".temp.wav")

        # Step 1: Convert image to WAV
        log(f"{log_prefix} 🔄 Converting {os.path.basename(image_file)} → {os.path.basename(wav_path)} ...")
        # Use explicit PCM format to ensure shnsplit compatibility (avoid WAVE_FORMAT_EXTENSIBLE)
        exit_code = run_command(
            ["ffmpeg", "-y", "-i", image_file, "-acodec", "pcm_s16le", 
             "-ar", "44100", "-ac", "2", wav_path], 
            logfile
        )
        if exit_code != 0:
            error_msg = f"ffmpeg conversion failed with exit code {exit_code}"
            log(f"{log_prefix} ❌ {error_msg}")
            log(f"{log_prefix} 📋 Command: ffmpeg -y -i {image_file} {wav_path}")
            log(f"{log_prefix} 📄 Full log available at: {logfile}")
            return {"status": "error", "message": error_msg, "log": logfile, "command": "ffmpeg"}
        log(f"{log_prefix} ✅ Conversion completed successfully")

        # Step 2: Ensure CUE file is in UTF-8
        utf8_cue_path, is_temp_cue = ensure_utf8_cue(
            cue_path, 
            lambda msg: log(f"{log_prefix} {msg}")
        )

        # Step 3: Split WAV using CUE sheet
        log(f"{log_prefix} ✂️ Splitting {os.path.basename(wav_path)} using CUE sheet...")
        
        # Prepare output format specification
        output_spec = _get_output_spec(output_format)
        
        # Change to working directory so shnsplit creates files in the right place
        original_cwd = os.getcwd()
        # Set UTF-8 locale for subprocess to handle accented characters
        env = os.environ.copy()
        env['LC_ALL'] = 'C.UTF-8'
        env['LANG'] = 'C.UTF-8'
        
        try:
            os.chdir(working_dir)
            # Use relative paths since we're now in the working directory
            exit_code = run_command(
                ["shnsplit", "-f", os.path.basename(utf8_cue_path), 
                 "-O", "never", "-o", output_spec, "-t", "%n. %t", 
                 os.path.basename(wav_path)], 
                logfile, env=env
            )
        finally:
            os.chdir(original_cwd)
        
        if exit_code != 0:
            error_msg = f"shnsplit failed with exit code {exit_code}"
            log(f"{log_prefix} ❌ {error_msg}")
            log(f"{log_prefix} 📋 Command: shnsplit -f {utf8_cue_path} -o {output_format} {working_dir}/track%02d {wav_path}")
            log(f"{log_prefix} 📄 Full log available at: {logfile}")
            # Clean up temp files before returning
            _cleanup_temp_files(is_temp_cue, utf8_cue_path, wav_path, log, log_prefix)
            return {"status": "error", "message": error_msg, "log": logfile, "command": "shnsplit"}
        log(f"{log_prefix} ✅ Splitting completed successfully")

        # Step 4: Tag tracks with metadata from CUE
        log(f"{log_prefix} 🎧 Tagging tracks with metadata from CUE...")
        track_files = [
            os.path.join(working_dir, f) 
            for f in sorted(os.listdir(working_dir)) 
            if f.lower().endswith(f".{output_format}")
        ]
        log(f"{log_prefix} 📊 Found {len(track_files)} track(s) to tag")
        
        if track_files:
            failed_tags = _tag_tracks(track_files, utf8_cue_path, logfile, env)
            if failed_tags:
                error_msg = f"cuetag failed for {len(failed_tags)} track(s): {', '.join(failed_tags)}"
                log(f"{log_prefix} ⚠️ {error_msg}")
            else:
                log(f"{log_prefix} ✅ Tagging completed successfully")
        
        # Clean up temporary UTF-8 CUE file if created (after tagging)
        if is_temp_cue and os.path.exists(utf8_cue_path):
            log(f"{log_prefix} 🗑️ Cleaning up temporary UTF-8 CUE file")
            os.remove(utf8_cue_path)

        # Step 5: Find album cover image
        cover_image = find_album_cover(working_dir, log)
        
        # Step 6: Optimize compression and embed album art
        log(f"{log_prefix} 🧠 Optimizing compression and embedding album art...")
        optimization_result = _optimize_tracks(
            working_dir, output_format, cover_image, log, logfile, log_prefix
        )
        
        if optimization_result["status"] != "success":
            # Clean up before returning error
            if os.path.exists(wav_path):
                log(f"{log_prefix} 🗑️ Removing temporary WAV file: {os.path.basename(wav_path)}")
                os.remove(wav_path)
            return optimization_result
        
        # Step 7: Clean up temporary WAV file
        log(f"{log_prefix} 🗑️ Removing temporary WAV file: {os.path.basename(wav_path)}")
        os.remove(wav_path)

        # Step 8: Clean up source files if requested
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


def _get_output_spec(output_format):
    """Get shnsplit output format specification"""
    if output_format == "flac":
        return "flac flac -8 -o %f -"
    elif output_format == "mp3":
        return "cust ext=mp3 ffmpeg -i - -codec:a libmp3lame -b:a 320k %f"
    elif output_format == "aac":
        return "cust ext=aac ffmpeg -i - -c:a aac -b:a 256k %f"
    return "flac flac -8 -o %f -"


def _cleanup_temp_files(is_temp_cue, utf8_cue_path, wav_path, log, log_prefix):
    """Clean up temporary files"""
    if is_temp_cue and os.path.exists(utf8_cue_path):
        os.remove(utf8_cue_path)
    if os.path.exists(wav_path):
        log(f"{log_prefix} 🗑️ Cleaning up temporary WAV file: {os.path.basename(wav_path)}")
        os.remove(wav_path)


def _tag_tracks(track_files, utf8_cue_path, logfile, env):
    """Tag tracks with metadata from CUE. Returns list of failed files."""
    failed_tags = []
    for track_file in track_files:
        exit_code = run_command(["cuetag", utf8_cue_path, track_file], logfile, env=env)
        if exit_code != 0:
            failed_tags.append(os.path.basename(track_file))
    return failed_tags


def _optimize_tracks(working_dir, output_format, cover_image, log, logfile, log_prefix):
    """
    Optimize track compression and embed album art.
    Returns result dictionary with status.
    """
    tmpdir = tempfile.mkdtemp()
    log(f"{log_prefix} 📁 Created temporary directory: {tmpdir}")
    
    optimization_count = 0
    skipped_count = 0
    
    try:
        for file in os.listdir(working_dir):
            if not file.lower().endswith(f".{output_format}"):
                continue
                
            src = os.path.join(working_dir, file)
            dst = os.path.join(tmpdir, file)

            cmd = _build_optimization_command(
                src, dst, output_format, cover_image, log, file, log_prefix
            )
            
            if cmd is None:
                # File already optimized, skip
                skipped_count += 1
                continue

            exit_code = run_command(cmd, logfile)
            if exit_code == 0:
                shutil.move(dst, src)
                optimization_count += 1
                log(f"{log_prefix}   ✅ {file}: optimization complete")
            else:
                error_msg = f"Optimization of {file} failed with exit code {exit_code}"
                log(f"{log_prefix}   ❌ {error_msg}")
                log(f"{log_prefix} 📄 Full log available at: {logfile}")
                # Clean up temporary directory before returning
                log(f"{log_prefix} 🗑️ Cleaning up temporary directory: {tmpdir}")
                shutil.rmtree(tmpdir, ignore_errors=True)
                return {"status": "error", "message": error_msg, "log": logfile, 
                       "command": "ffmpeg-optimize"}

        log(f"{log_prefix} 📊 Optimization summary: {optimization_count} optimized, {skipped_count} skipped")
        
    finally:
        log(f"{log_prefix} 🗑️ Cleaning up temporary directory: {tmpdir}")
        shutil.rmtree(tmpdir, ignore_errors=True)
    
    return {"status": "success"}


def _build_optimization_command(src, dst, output_format, cover_image, log, filename, log_prefix):
    """
    Build ffmpeg command for track optimization.
    Returns None if file is already optimized and should be skipped.
    """
    cmd = []
    
    if output_format == "flac":
        # Check if already at max compression
        result = subprocess.run(
            ["metaflac", "--show-compression-level", src], 
            capture_output=True, text=True
        )
        if result.returncode == 0 and "level 8" in result.stdout:
            log(f"{log_prefix}   ✅ {filename}: already max compression (level 8)")
            return None
            
        log(f"{log_prefix}   🔧 Optimizing {filename} to compression level 8...")
        if cover_image:
            cmd = [
                "ffmpeg", "-y", "-i", src, "-i", cover_image, 
                "-map", "0:0", "-map", "1", 
                "-c:a", "flac", "-compression_level", "8", 
                "-c:v", "copy", "-disposition:v", "attached_pic", 
                "-metadata:s:v", "title=Album cover", 
                "-metadata:s:v", "comment=Cover (front)", 
                dst
            ]
        else:
            cmd = [
                "ffmpeg", "-y", "-i", src, 
                "-c:a", "flac", "-compression_level", "8", 
                dst
            ]
            
    elif output_format == "mp3":
        log(f"{log_prefix}   🔧 Encoding {filename} to MP3 320k...")
        if cover_image:
            cmd = [
                "ffmpeg", "-y", "-i", src, "-i", cover_image, 
                "-map", "0:0", "-map", "1:0", 
                "-c", "copy", "-id3v2_version", "3", 
                "-metadata:s:v", "title=Album cover", 
                "-metadata:s:v", "comment=Cover (front)", 
                dst
            ]
        else:
            cmd = [
                "ffmpeg", "-y", "-i", src, 
                "-codec:a", "libmp3lame", "-b:a", "320k", 
                dst
            ]
            
    elif output_format == "aac":
        log(f"{log_prefix}   🔧 Encoding {filename} to AAC 256k...")
        cmd = [
            "ffmpeg", "-y", "-i", src, 
            "-c:a", "aac", "-b:a", "256k", 
            dst
        ]

    return cmd
