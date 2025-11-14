# Project Structure

This document describes the refactored project structure for the CUE Splitter HTTP Daemon.

## Directory Layout

```
cue-to-tracks-server/
├── src/
│   └── cue_splitter/              # Main package
│       ├── __init__.py            # Package initialization
│       ├── api/                   # HTTP API layer
│       │   ├── __init__.py
│       │   └── server.py          # HTTP server and request handlers
│       ├── core/                  # Core business logic
│       │   ├── __init__.py
│       │   ├── audio_processor.py # Single pair audio processing
│       │   ├── file_finder.py     # File discovery utilities
│       │   └── job_orchestrator.py# Multi-pair job orchestration
│       ├── utils/                 # Utility functions
│       │   ├── __init__.py
│       │   ├── encoding.py        # Encoding detection/conversion
│       │   └── helpers.py         # General helper functions
│       └── workers/               # Worker thread management
│           ├── __init__.py
│           └── processor.py       # Worker thread implementation
├── main.py                        # Application entry point
├── Dockerfile                     # Docker container definition
├── requirements.txt               # Python dependencies
├── README.md                      # User documentation
└── ARCHITECTURE.md                # This file

## Module Responsibilities

### `main.py`
- Application entry point
- Command-line argument parsing
- Configuration from environment variables
- Signal handling for graceful shutdown
- Coordination of server and worker startup/shutdown

### `api/server.py`
- HTTP server implementation using `http.server.HTTPServer`
- Request routing and handling
- Job submission endpoint (`POST /process`)
- Status checking endpoint (`GET /status`)
- Log retrieval endpoint (`GET /log/<id>`)
- Thread-safe results storage

### `core/file_finder.py`
- Recursive directory traversal
- CUE + audio image pair detection
- Album cover image discovery
- Smart matching of filenames with different patterns

### `core/audio_processor.py`
- Single CUE+image pair processing
- Audio format conversion (using ffmpeg)
- Track splitting (using shnsplit)
- Metadata tagging (using cuetag)
- Compression optimization
- Album art embedding

### `core/job_orchestrator.py`
- Multi-pair job coordination
- Parallel processing with ThreadPoolExecutor
- Progress tracking and logging
- Result aggregation
- Error handling and recovery

### `workers/processor.py`
- Worker thread lifecycle management
- Task queue consumption
- Job status updates
- Graceful shutdown handling

### `utils/helpers.py`
- Safe printing with Unicode handling
- Command execution with logging
- Common utility functions

### `utils/encoding.py`
- Character encoding detection (using chardet)
- UTF-8 conversion for CUE files
- Temporary file management

## Data Flow

1. **Job Submission**
   ```
   HTTP POST /process
   → CueSplitHandler.do_POST()
   → Task added to queue
   → Response with job_id
   ```

2. **Job Processing**
   ```
   Worker thread pulls from queue
   → job_orchestrator.split_and_encode()
   → file_finder.find_cue_image_pairs()
   → For each pair (parallel):
       → audio_processor.process_single_pair()
           → Convert image to WAV (ffmpeg)
           → Ensure UTF-8 encoding (chardet)
           → Split tracks (shnsplit)
           → Tag metadata (cuetag)
           → Optimize compression (ffmpeg)
           → Embed album art
   → Aggregate results
   → Update job status
   ```

3. **Status Check**
   ```
   HTTP GET /status
   → CueSplitHandler.do_GET()
   → Return all job statuses
   ```

4. **Log Retrieval**
   ```
   HTTP GET /log/<job_id>
   → CueSplitHandler.do_GET()
   → Read log file from /tmp/cue_split_logs/
   → Return log content
   ```

## Threading Model

- **Main Thread**: Runs HTTP server with 1-second timeout for shutdown checks
- **Worker Threads**: Process jobs from queue (configurable count)
- **Processing Threads**: Within each job, pairs are processed in parallel (configurable)

Thread safety is ensured through:
- `queue.Queue` for task distribution
- `threading.Lock` for shared state access
- `threading.Event` for shutdown signaling

## Configuration

Configuration can be set via command-line arguments or environment variables:

| Argument | Environment | Default | Description |
|----------|-------------|---------|-------------|
| `--port` | - | 8080 | HTTP server port |
| `--threads` | `THREADS` | CPU count | Number of job workers |
| `--pair-threads` | `PAIR_THREADS` | Auto | Parallel pairs per job |
| `--format` | `FORMAT` | flac | Output format (flac/mp3/aac) |
| `--no-cleanup` | `NO_CLEANUP` | false | Keep source files |

## Error Handling

- **Command failures**: Each subprocess call checks exit codes
- **Encoding issues**: Automatic detection and conversion
- **Partial failures**: Jobs can succeed partially (some pairs fail)
- **Cleanup**: Temporary files removed even on errors
- **Logging**: Comprehensive logging to job-specific files

## Extension Points

To add new features:

1. **New output format**: Extend `_get_output_spec()` in `audio_processor.py`
2. **New API endpoint**: Add handler in `CueSplitHandler` class
3. **Custom processing**: Create new module in `core/` and import in orchestrator
4. **Additional utilities**: Add to appropriate `utils/` module

## Benefits of This Architecture

1. **Separation of Concerns**: Each module has a clear, single responsibility
2. **Testability**: Individual modules can be unit tested independently
3. **Maintainability**: Changes to one layer don't affect others
4. **Scalability**: Easy to add features or modify behavior
5. **Readability**: Clear module structure makes code navigation easier
6. **Reusability**: Core logic can be imported and used in other contexts

## Migration from Old Structure

The original monolithic `split_cue_server.py` (631 lines) has been split into:
- 8 focused modules (~150 lines each)
- Clear separation between HTTP, processing, and utility concerns
- Better error handling and logging
- More maintainable and testable code

The external API and functionality remain identical.
