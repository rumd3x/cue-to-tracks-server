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

## Supported Input Formats

- APE (Monkey's Audio)
- FLAC
- WAV
- WavPack (WV)

## Output Formats

- **FLAC**: Compression level 8 (default)
- **MP3**: 320 kbps CBR
- **AAC**: 256 kbps

## Requirements

- Python 3.12+
- ffmpeg
- cuetools
- shntool
- flac

## Installation

### Docker (Recommended)

**Note:** A pre-built public image is available at `edmur/cue-to-tracks-server:latest` if you don't want to build the image yourself.

#### Using Pre-built Image

```bash
docker run -d \
  -p 8080:8080 \
  -v /path/to/music:/music \
  edmur/cue-to-tracks-server:latest
```

#### Building the Image

```bash
docker build . -t cue-splitter
docker run -d -p 8080:8080 -v /path/to/music:/music cue-splitter
```

### Manual Installation

```bash
# Install dependencies (Debian/Ubuntu)
apt-get install ffmpeg cuetools shntool flac python3

# Run the server
python3 split_cue_server.py
```

## Usage

### Starting the Server

```bash
python3 split_cue_server.py [OPTIONS]
```

#### Options

- `--port <PORT>`: HTTP server port (default: 8080)
- `--threads <N>`: Number of job worker threads (default: CPU count)
- `--pair-threads <N>`: Max parallel pair processing within a job (default: auto)
- `--format <FORMAT>`: Output audio format: flac, mp3, or aac (default: flac)
- `--no-cleanup`: Keep original CUE and image files after processing

### API Endpoints

#### Submit a Job

```bash
POST /process
Content-Type: application/json

{
  "path": "/path/to/album/directory"
}
```

**Response:**
```json
{
  "job_id": "1",
  "status": "queued"
}
```

#### Check Job Status

```bash
GET /status
```

**Response:**
```json
{
  "1": {
    "status": "success",
    "path": "/path/to/album",
    "log": "/tmp/cue_split_logs/1.log"
  }
}
```

#### Get Job Log

```bash
GET /log/<job_id>
```

**Response:**
```json
{
  "job_id": "1",
  "log": "..."
}
```

### Example

```bash
# Submit a job to process an album
curl -X POST http://localhost:8080/process \
  -H "Content-Type: application/json" \
  -d '{"path": "/music/Artist - Album"}'

# Check all job statuses
curl http://localhost:8080/status

# Get log for job ID 1
curl http://localhost:8080/log/1
```

## How It Works

1. **Search**: Recursively scans the provided directory for CUE+image file pairs
2. **Convert**: Converts audio image files (APE/FLAC/WAV/WV) to WAV format
3. **Split**: Uses CUE sheet to split WAV into individual tracks
4. **Tag**: Applies metadata from CUE sheet to each track
5. **Optimize**: Re-encodes with optimal compression and embeds album art
6. **Cleanup**: (Optional) Removes original CUE and image files

## Album Art Detection

The tool automatically searches for album cover images with the following priority:

1. Images with "front" in the filename (case insensitive)
2. First image without "back", "side", or "inner" in the filename

Supported image formats: JPG, PNG, BMP, GIF, TIFF, WebP

## Logging

Detailed logs for each job are stored in `/tmp/cue_split_logs/<job_id>.log` and include:

- Processing steps and timestamps
- Command outputs
- Error messages and stack traces
- Optimization statistics

## Docker Configuration

The included Dockerfile creates a lightweight container with all dependencies pre-installed. Mount your music directory as a volume to process files.

### Environment Variables

The Docker image supports configuration via environment variables:

- `THREADS`: Number of job worker threads (default: `4`)
- `PAIR_THREADS`: Max parallel pair processing within a job (default: `2`)
- `FORMAT`: Output audio format - `flac`, `mp3`, or `aac` (default: `flac`)
- `NO_CLEANUP`: Keep original CUE and image files after processing - `true` or `false` (default: `false`)

### Docker Run Examples

Basic usage:
```bash
docker run -d \
  -p 8080:8080 \
  -v /path/to/music:/music \
  --name cue-splitter \
  edmur/cue-to-tracks-server:latest
```

With custom configuration using environment variables:
```bash
docker run -d \
  -p 8080:8080 \
  -v /path/to/music:/music \
  -e THREADS=8 \
  -e PAIR_THREADS=4 \
  -e FORMAT=mp3 \
  -e NO_CLEANUP=true \
  --name cue-splitter \
  edmur/cue-to-tracks-server:latest
```

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
