# Multi-Image CUE File Support

## Overview

This enhancement adds support for CUE files that reference multiple audio files (multi-image CUE sheets). Previously, `shnsplit` would fail to process such files, but now they are automatically split into separate single-image CUE files.

## Problem

`shnsplit` cannot process CUE files that contain multiple `FILE` directives. For example:

```cue
PERFORMER "Artist"
TITLE "Album"
FILE "disc1.flac" WAVE
  TRACK 01 AUDIO
    TITLE "Track 1"
    INDEX 01 00:00:00
FILE "disc2.flac" WAVE
  TRACK 02 AUDIO
    TITLE "Track 2"
    INDEX 01 00:00:00
```

## Solution

When a CUE file with multiple `FILE` directives is detected, the system now:

1. **Detects** multi-image CUE files during the scanning phase
2. **Splits** them into separate CUE files, one per audio file:
   - `album.cue` → `album_part1.cue`, `album_part2.cue`, etc.
3. **Processes** each split CUE file + audio file pair independently
4. **Cleans up** split CUE files after processing (when cleanup is enabled)

## Implementation Details

### Modified Files

1. **`src/cue_splitter/core/file_finder.py`**
   - Added `_split_multi_image_cue()` function to split multi-image CUE files
   - Modified `find_cue_image_pairs()` to detect and split multi-image CUEs
   - Returns pairs referencing the newly created single-image CUE files

2. **`src/cue_splitter/core/audio_processor.py`**
   - Enhanced cleanup logic to remove original multi-image CUE files
   - Cleanup only occurs after all split parts have been processed

### Key Features

- **Preserves metadata**: Global CUE metadata (PERFORMER, TITLE, etc.) is copied to each split file
- **Maintains track numbering**: Original track numbers are preserved in split files
- **Case-insensitive matching**: Audio files are matched case-insensitively for cross-platform compatibility
- **Automatic cleanup**: Split CUE files are cleaned up along with original files when `--no-cleanup` is not set

### Example

**Input:**
```
album/
  ├── album.cue          (references disc1.flac and disc2.flac)
  ├── disc1.flac
  └── disc2.flac
```

**After scanning:**
```
album/
  ├── album.cue          (original, will be cleaned up)
  ├── album_part1.cue    (references only disc1.flac)
  ├── album_part2.cue    (references only disc2.flac)
  ├── disc1.flac
  └── disc2.flac
```

**After processing:**
```
album/
  ├── 01. Track 1.flac
  ├── 02. Track 2.flac
  ├── 03. Track 3.flac
  └── 04. Track 4.flac
```

## Testing

Comprehensive tests have been added to verify:
- ✅ Single-image CUE files still work as before
- ✅ Multi-image CUE files are correctly split
- ✅ Each split CUE contains exactly one FILE directive
- ✅ Track numbers are preserved
- ✅ Case-insensitive file matching works
- ✅ Cleanup removes all temporary files

Run tests with:
```bash
python3 test_comprehensive.py
```

## Backward Compatibility

This enhancement is fully backward compatible:
- Single-image CUE files work exactly as before
- No changes to API or command-line interface
- No changes to output format or structure
