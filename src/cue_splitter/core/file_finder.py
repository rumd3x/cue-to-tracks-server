"""File discovery and searching utilities"""
import os
import re
import cueparser


def _parse_cue_file(cue_path):
    """
    Parse a CUE file using cueparser library.
    
    Args:
        cue_path: Path to the CUE file
        
    Returns:
        CueSheet object if successful, None otherwise
    """
    try:
        cue_sheet = cueparser.CueSheet()
        cue_sheet.setOutputFormat('', '')
        
        with open(cue_path, 'r', encoding='utf-8', errors='ignore') as f:
            cue_sheet.setData(f.read())
            cue_sheet.parse()
        
        return cue_sheet
    except Exception:
        return None


def _extract_audio_files_from_cuesheet(cue_sheet):
    """
    Extract all audio file names from a parsed CueSheet.
    
    Args:
        cue_sheet: Parsed CueSheet object
        
    Returns:
        List of audio file names referenced in FILE directives
    """
    file_pattern = re.compile(r'^FILE\s+"([^"]+)"\s+', re.IGNORECASE)
    audio_files = []
    
    for line in cue_sheet.data:
        match = file_pattern.match(line)
        if match:
            audio_files.append(match.group(1))
    
    return audio_files


def _split_multi_image_cue(cue_path, cue_sheet, audio_files, log_func):
    """
    Split a CUE file that references multiple audio files into separate CUE files.
    
    Args:
        cue_path: Path to the original CUE file
        cue_sheet: Parsed CueSheet object
        audio_files: List of audio file names referenced in the CUE
        log_func: Function to call for logging messages
        
    Returns:
        List of tuples: [(new_cue_path, audio_file_name), ...]
    """
    try:
        cue_dir = os.path.dirname(cue_path)
        cue_basename = os.path.splitext(os.path.basename(cue_path))[0]
        created_cues = []
        
        # Find global metadata (before first FILE directive)
        global_metadata = []
        file_sections = {}
        current_file = None
        current_section = []
        file_pattern = re.compile(r'^\s*FILE\s+"([^"]+)"\s+(\w+)', re.IGNORECASE)
        
        for line in cue_sheet.data:
            file_match = file_pattern.match(line)
            
            if file_match:
                # Save previous section if exists
                if current_file:
                    file_sections[current_file] = current_section
                
                # Start new section
                current_file = file_match.group(1)
                current_section = [line]
            elif current_file:
                # We're inside a file section
                current_section.append(line)
            else:
                # We're in global metadata
                global_metadata.append(line)
        
        # Don't forget the last section
        if current_file:
            file_sections[current_file] = current_section
        
        # Create separate CUE files for each audio file
        for i, audio_file in enumerate(audio_files, 1):
            if audio_file not in file_sections:
                log_func(f"    ⚠️  Audio file {audio_file} not found in parsed CUE sections")
                continue
            
            # Generate new CUE filename
            if len(audio_files) > 1:
                new_cue_name = f"{cue_basename}_part{i}.cue"
            else:
                new_cue_name = f"{cue_basename}.cue"
            
            new_cue_path = os.path.join(cue_dir, new_cue_name)
            
            # Build new CUE content
            new_cue_lines = global_metadata + file_sections[audio_file]
            new_cue_content = '\n'.join(new_cue_lines)
            
            # Write new CUE file
            with open(new_cue_path, 'w', encoding='utf-8') as f:
                f.write(new_cue_content)
            
            created_cues.append((new_cue_path, audio_file))
            log_func(f"    ✅ Created single-image CUE: {new_cue_name} → {audio_file}")
        
        return created_cues
        
    except Exception as e:
        log_func(f"    ⚠️  Error splitting multi-image CUE: {str(e)}")
        return []


def find_album_cover(album_path, log_func):
    """
    Search for album cover image in the album directory and subdirectories.
    Priority:
    1. Images with "front" in the name (case insensitive)
    2. First image without "back", "side", or "inner" in the name
    
    Args:
        album_path: Path to the album directory
        log_func: Function to call for logging messages
        
    Returns:
        Path to cover image or None
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
                
                if "front" in file_lower or file_lower in ["f", "jc"]:
                    front_images.append(file_path)
                elif "cover" in file_lower or "poster" in file_lower or "scan" in file_lower:
                    front_images.append(file_path)
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


def _extract_referenced_files_from_cue(cue_path, log_func):
    """
    Parse a CUE file and extract the audio files referenced in FILE directives.
    
    Args:
        cue_path: Path to the CUE file
        log_func: Function to call for logging messages
        
    Returns:
        Tuple of (CueSheet object, list of audio file names), or (None, None) if parsing fails
    """
    try:
        cue_sheet = _parse_cue_file(cue_path)
        if not cue_sheet:
            log_func(f"    ⚠️  Error parsing CUE file")
            return None, None
        
        audio_files = _extract_audio_files_from_cuesheet(cue_sheet)
        return cue_sheet, audio_files if audio_files else None
        
    except Exception as e:
        log_func(f"    ⚠️  Error parsing CUE file: {str(e)}")
        return None, None


def _find_audio_file(audio_file_name, dirpath, filenames):
    """
    Locate an audio file in the directory, trying exact match first, then case-insensitive.
    
    Args:
        audio_file_name: Name of the audio file to find
        dirpath: Directory to search in
        filenames: List of files in the directory
        
    Returns:
        Full path to the audio file if found, None otherwise
    """
    # Try exact match first
    audio_file_path = os.path.join(dirpath, audio_file_name)
    if os.path.exists(audio_file_path):
        return audio_file_path
    
    # Try case-insensitive search (for Linux compatibility)
    for existing_file in filenames:
        if existing_file.lower() == audio_file_name.lower():
            return os.path.join(dirpath, existing_file)
    
    return None


def _find_audio_file_fallback(cue_path, dirpath, filenames, log_func):
    """
    Try to find an audio file matching the CUE file when the FILE directive fails.
    
    Fallback strategies:
    1. Try cue_basename + audio extensions (e.g., album.cue -> album.flac)
    2. If CUE filename ends with audio extension (e.g., album.flac.cue),
       try removing .cue (e.g., album.flac)
    
    Args:
        cue_path: Path to the CUE file
        dirpath: Directory containing the CUE file
        filenames: List of files in the directory
        log_func: Function to call for logging messages
        
    Returns:
        Path to audio file if found, None otherwise
    """
    audio_extensions = [".ape", ".flac", ".wav", ".wv"]
    cue_filename = os.path.basename(cue_path)
    cue_basename = os.path.splitext(cue_filename)[0]
    
    # Fallback 1: Try cue_basename + audio extensions
    log_func(f"    🔍 Fallback: Trying to find audio file with same name as CUE...")
    for ext in audio_extensions:
        candidate = cue_basename + ext
        candidate_path = os.path.join(dirpath, candidate)
        
        if os.path.exists(candidate_path):
            log_func(f"    ✅ Found matching audio file: {candidate}")
            return candidate_path
        
        # Try case-insensitive match
        for existing_file in filenames:
            if existing_file.lower() == candidate.lower():
                audio_file_path = os.path.join(dirpath, existing_file)
                log_func(f"    ✅ Found matching audio file (case-insensitive): {existing_file}")
                return audio_file_path
    
    # Fallback 2: Check if CUE filename already ends with an audio extension
    for ext in audio_extensions:
        if cue_basename.lower().endswith(ext.lower()):
            candidate = cue_basename
            candidate_path = os.path.join(dirpath, candidate)
            
            log_func(f"    🔍 Fallback: CUE name ends with audio extension, trying {candidate}...")
            
            if os.path.exists(candidate_path):
                log_func(f"    ✅ Found matching audio file: {candidate}")
                return candidate_path
            
            # Try case-insensitive match
            for existing_file in filenames:
                if existing_file.lower() == candidate.lower():
                    audio_file_path = os.path.join(dirpath, existing_file)
                    log_func(f"    ✅ Found matching audio file (case-insensitive): {existing_file}")
                    return audio_file_path
    
    log_func(f"    ❌ Could not find audio file through fallback methods")
    return None


def _match_audio_file_with_fallback(cue_path, audio_file_name, dirpath, filenames, log_func):
    """
    Try to match an audio file, with fallback strategies if not found directly.
    
    Args:
        cue_path: Path to the CUE file
        audio_file_name: Name of the audio file referenced in the CUE
        dirpath: Directory containing the files
        filenames: List of files in the directory
        log_func: Function to call for logging messages
        
    Returns:
        Path to the matched audio file, or None if not found
    """
    # Try to find the audio file directly
    audio_file_path = _find_audio_file(audio_file_name, dirpath, filenames)
    
    if audio_file_path:
        return audio_file_path
    
    # If not found, try fallback methods
    return _find_audio_file_fallback(cue_path, dirpath, filenames, log_func)


def _process_multi_image_cue(cue_path, cue_sheet, audio_files, dirpath, filenames, log_func):
    """
    Process a CUE file that references multiple audio files.
    
    Splits the multi-image CUE into separate single-image CUE files and matches
    each with its corresponding audio file.
    
    Args:
        cue_path: Path to the original CUE file
        cue_sheet: Parsed CueSheet object
        audio_files: List of audio file names referenced in the CUE
        dirpath: Directory containing the CUE file
        filenames: List of files in the directory
        log_func: Function to call for logging messages
        
    Returns:
        List of tuples: [(cue_path, audio_path, dirpath), ...]
    """
    pairs = []
    log_func(f"    🔪 Multi-image CUE detected! Creating separate CUE files...")
    created_cues = _split_multi_image_cue(cue_path, cue_sheet, audio_files, log_func)
    
    for new_cue_path, audio_file_name in created_cues:
        audio_file_path = _match_audio_file_with_fallback(
            new_cue_path, audio_file_name, dirpath, filenames, log_func
        )
        
        if audio_file_path:
            pairs.append((new_cue_path, audio_file_path, dirpath))
        else:
            log_func(f"    ❌ Audio file not found: {audio_file_name}")
    
    return pairs


def _process_single_image_cue(cue_path, cue_file, audio_file_name, dirpath, filenames, log_func):
    """
    Process a CUE file that references a single audio file.
    
    Args:
        cue_path: Path to the CUE file
        cue_file: Name of the CUE file (for logging)
        audio_file_name: Name of the audio file referenced in the CUE
        dirpath: Directory containing the CUE file
        filenames: List of files in the directory
        log_func: Function to call for logging messages
        
    Returns:
        Tuple (cue_path, audio_path, dirpath) if matched, None otherwise
    """
    audio_file_path = _find_audio_file(audio_file_name, dirpath, filenames)
    
    if audio_file_path:
        log_func(f"    ✅ Matched: {cue_file} → {audio_file_name}")
        return (cue_path, audio_file_path, dirpath)
    
    # Try fallback methods
    audio_file_path = _find_audio_file_fallback(cue_path, dirpath, filenames, log_func)
    
    if audio_file_path:
        return (cue_path, audio_file_path, dirpath)
    
    log_func(f"    ❌ Audio file not found: {audio_file_name}")
    return None


def find_cue_image_pairs(root_path, log_func=None):
    """
    Recursively search for CUE + image file pairs in root_path and all subdirectories.
    
    Parses each .cue file to extract the FILE directive(s) that specify the associated
    audio file(s). Supports CUE files that reference single or multiple audio files.
    
    For CUE files with multiple FILE directives (multi-image CUE sheets), this function
    automatically splits them into separate CUE files, one for each audio file. This is
    necessary because shnsplit cannot process CUE files with multiple images.
    
    Args:
        root_path: Root directory to search
        log_func: Optional function to call for logging messages
        
    Returns:
        List of tuples: [(cue_path, image_path, containing_dir), ...]
        Note: If a CUE file references multiple audio files, multiple pairs are returned,
        one for each audio file, with each pair referencing a newly created single-image
        CUE file (e.g., "album_part1.cue", "album_part2.cue").
    """
    if log_func is None:
        log_func = lambda msg: None
    
    pairs = []
    
    for dirpath, dirnames, filenames in os.walk(root_path):
        cue_files = [f for f in filenames if f.lower().endswith(".cue")]
        
        if cue_files:
            rel_dir = os.path.relpath(dirpath, root_path) if dirpath != root_path else "."
            log_func(f"📁 Scanning directory: {rel_dir}")
        
        for cue_file in cue_files:
            cue_path = os.path.join(dirpath, cue_file)
            log_func(f"  📄 Found CUE file: {cue_file}")
            
            # Extract audio file references from the CUE
            cue_sheet, audio_files = _extract_referenced_files_from_cue(cue_path, log_func)
            
            if not audio_files:
                log_func(f"    ⚠️  No FILE directives found in {cue_file}")
                continue
            
            log_func(f"    🔗 Found {len(audio_files)} audio file reference(s) in CUE")
            
            # Process based on whether it's single or multi-image CUE
            if len(audio_files) > 1:
                # Multi-image CUE: split into separate CUE files
                new_pairs = _process_multi_image_cue(
                    cue_path, cue_sheet, audio_files, dirpath, filenames, log_func
                )
                pairs.extend(new_pairs)
            else:
                # Single-image CUE: match directly
                pair = _process_single_image_cue(
                    cue_path, cue_file, audio_files[0], dirpath, filenames, log_func
                )
                if pair:
                    pairs.append(pair)
    
    return pairs
