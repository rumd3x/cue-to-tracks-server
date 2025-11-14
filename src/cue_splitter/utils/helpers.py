"""General utility functions"""
import sys
import subprocess


def safe_print(msg):
    """Print with handling for surrogate characters that can't be encoded"""
    try:
        print(msg)
    except UnicodeEncodeError:
        # Replace problematic characters with safe representation
        safe_msg = msg.encode('utf-8', errors='replace').decode('utf-8')
        print(safe_msg)
    sys.stdout.flush()


def run_command(cmd, logfile, env=None):
    """
    Execute a shell command and log output to a file.
    
    Args:
        cmd: Command and arguments as a list
        logfile: Path to log file for output
        env: Optional environment variables dict
        
    Returns:
        Exit code of the command
    """
    with open(logfile, "a", encoding="utf-8", errors="replace") as f:
        # Handle potential encoding issues in command strings
        try:
            cmd_str = ' '.join(str(c) for c in cmd)
        except UnicodeEncodeError:
            # If there are encoding issues, use repr() to show the command safely
            cmd_str = ' '.join(repr(c) for c in cmd)
        
        f.write(f"\n$ {cmd_str}\n")
        f.flush()
        result = subprocess.run(cmd, stdout=f, stderr=f, check=False, env=env)
        f.write(f"[Exit code: {result.returncode}]\n")
        f.flush()
        return result.returncode
