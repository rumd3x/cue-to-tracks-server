# CUE Splitter HTTP Daemon

A multi-threaded HTTP daemon for processing CUE sheet + audio image file pairs. Automatically converts, splits, tags, and optimizes audio files based on CUE sheets.

## Features

- 🔍 **Recursive Search**: Automatically finds CUE+image pairs in directory trees
- ⚡ **Parallel Processing**: Multi-threaded job queue with concurrent pair processing
- 🎵 **Multiple Formats**: Supports FLAC, MP3, and AAC output
- 🎨 **Album Art**: Automatically embeds album covers into tracks
- 🏷️ **Metadata Tagging**: Tags tracks with metadata from CUE sheets
- 🗜️ **Smart Optimization**: FLAC compression level 8, MP3 320k, AAC 256k
- 📊 **Job Management**: HTTP API for submitting jobs and checking status
- 🐳 **Docker Ready**: Includes Dockerfile for containerized deployment

## How It Works

1. **Search**: Recursively scans the provided directory for CUE+image file pairs
2. **Convert**: Converts audio image files (APE/FLAC/WAV/WV) to WAV format
3. **Split**: Uses CUE sheet to split WAV into individual tracks
4. **Tag**: Applies metadata from CUE sheet to each track
5. **Optimize**: Re-encodes with optimal compression and embeds album art
6. **Cleanup**: (Optional) Removes original CUE and image files

### Supported Input Formats

- APE (Monkey's Audio)
- FLAC
- WAV
- WavPack (WV)

### Output Formats

- **FLAC**: Compression level 8 (default)
- **MP3**: 320 kbps CBR
- **AAC**: 256 kbps

## Usage

### Starting the Server

```bash
python3 main.py [OPTIONS]
```

#### Options

- `--port <PORT>`: HTTP server port (default: 8080)
- `--threads <N>`: Number of job worker threads (default: CPU count)
- `--pair-threads <N>`: Max parallel pair processing within a job (default: auto)
- `--format <FORMAT>`: Output audio format: flac, mp3, or aac (default: flac)
- `--no-cleanup`: Keep original CUE and image files after processing

## Installation

### 🐳 Docker (Recommended)

The dockerized version is a lightweight container with all dependencies pre-installed. Mount your music directory as a volume and process your albums.

<details>
  <summary>Click to expand</summary>

#### Environment Variables

The Docker image supports configuration via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `THREADS` | Number of job worker threads | `4` |
| `PAIR_THREADS` | Max parallel pair processing within a job | `2` |
| `FORMAT` | Output audio format - `flac`, `mp3`, or `aac` | `flac` |
| `NO_CLEANUP` | Keep original CUE and image files after processing - `true` or `false` | `false` |
| `CUE_SPLITTER_DB` | Path to SQLite database file for job persistence | `/data/cue_splitter_jobs.db` |

With custom configuration using environment variables:
```bash
docker build . -t cue-splitter

docker run -d \
  -p 8080:8080 \
  -v /path/to/music:/music \
  -v /path/to/data:/data \
  -e THREADS=8 \
  -e PAIR_THREADS=4 \
  -e FORMAT=mp3 \
  -e NO_CLEANUP=true \
  --name cue-splitter \
  cue-splitter
```

**Volumes:**
- `/music`: Mount your music directory here for processing
- `/data`: Database storage for job persistence across container restarts

**Note:** A pre-built public image is available at `edmur/cue-to-tracks-server:latest` if you don't want to build the image yourself.

```bash
docker run -d \
  -p 8080:8080 \
  -v /path/to/music:/music \
  -v /path/to/data:/data \
  edmur/cue-to-tracks-server:latest
```

---

</details>


### ⚡ Manual Installation (Advanced)

<details>
  <summary>Click to expand</summary>
  
#### Requirements

- Python 3
- ffmpeg
- cuetools
- shntool
- flac
```bash
# Install dependencies (Debian/Ubuntu)
apt-get install ffmpeg cuetools shntool flac python3 python3-pip

# Install Python dependencies
pip3 install -r requirements.txt

# Run the server
python3 main.py
```

---

</details>

## API Endpoints

#### Submit a Job

```bash
POST /process
```

<details>
  <summary>Click to expand</summary>

```bash
# Submit a job to process an album
curl -X POST http://localhost:8080/process \
  -H "Content-Type: application/json" \
  -d '{"path": "/music/Artist - Album"}'
```

**Response:**
```json
{
  "job_id": "1",
  "status": "queued"
}
```
</details>

---

#### Check all Jobs Status


```bash
GET /status
```
<details>
  <summary>Click to expand</summary>

```bash
curl http://localhost:8080/status
```

**Response:**
```json
{
  "1": {
    "status": "error",
    "path": "/data/Downloads/out/lidarr/Iron Maiden - 1980 - Iron Maiden (Japanese TOCP-50691)",
    "message": "all 1 pair(s) failed",
    "log": "/tmp/cue_split_logs/1.log",
    "details": [
      {
      "status": "error",
      "message": "shnsplit failed with exit code 1",
      "log": "/tmp/cue_split_logs/1.log",
      "command": "shnsplit"
      }
    ]
  },
  "2": {
    "status": "success",
    "path": "/data/Downloads/out/lidarr/Iron Maiden - 1981- Killers (TOCP-53757, 2006)",
    "log": "/tmp/cue_split_logs/3.log",
    "details": [
      {
      "status": "success",
      "log": "/tmp/cue_split_logs/3.log"
      }
    ]
  }
}
```
</details>

---

#### Check Specific Job Status

```bash
GET /status/<job_id>
```

<details>
  <summary>Click to expand</summary>

```bash
curl http://localhost:8080/status/1
```

**Response:**
```json
{
  "job_id": "1",
  "status": "error",
  "path": "/data/Downloads/out/lidarr/Iron Maiden - 1980 - Iron Maiden (Japanese TOCP-50691)",
  "message": "all 1 pair(s) failed",
  "log": "/tmp/cue_split_logs/1.log",
  "details": [
    {
      "status": "error",
      "message": "shnsplit failed with exit code 1",
      "log": "/tmp/cue_split_logs/1.log",
      "command": "shnsplit"
    }
  ]
}
```

**Note:** Returns 404 if job ID doesn't exist.

</details>

---

#### Get Job Log


  
```bash
GET /log/<job_id>
```

<details>
  <summary>Click to expand</summary>

```bash
curl http://localhost:8080/log/1
```

**Response:**
```json
{
  "job_id": "1",
  "log": "..."
}
```
</details>

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
