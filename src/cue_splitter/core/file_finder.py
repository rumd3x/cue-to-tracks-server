"""File discovery and searching utilities"""
import os
import re
import cueparser


def _split_multi_image_cue(cue_path, referenced_files, log_func):
    """
    Split a CUE file that references multiple audio files into separate CUE files.
    
    Args:
        cue_path: Path to the original CUE file
        referenced_files: List of audio file names referenced in the CUE
        log_func: Function to call for logging messages
        
    Returns:
        List of tuples: [(new_cue_path, audio_file_name), ...]
    """
    try:
        # Read the original CUE file
        with open(cue_path, 'r', encoding='utf-8', errors='ignore') as f:
            cue_content = f.read()
        
        cue_dir = os.path.dirname(cue_path)
        cue_basename = os.path.splitext(os.path.basename(cue_path))[0]
        
        created_cues = []
        
        # Parse CUE content into lines
        lines = cue_content.split('\n')
        
        # Find global metadata (before first FILE directive)
        global_metadata = []
        file_sections = {}
        current_file = None
        current_section = []
        
        for line in lines:
            # Check if this is a FILE directive
            file_match = re.match(r'^\s*FILE\s+"([^"]+)"\s+(\w+)', line, re.IGNORECASE)
            
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
        for i, audio_file in enumerate(referenced_files, 1):
            if audio_file not in file_sections:
                log_func(f"    ⚠️  Audio file {audio_file} not found in parsed CUE sections")
                continue
            
            # Generate new CUE filename
            if len(referenced_files) > 1:
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
    # Default no-op logging function
    if log_func is None:
        log_func = lambda msg: None
    
    pairs = []
    # Regex pattern to match FILE directives in CUE files
    # Matches: FILE "filename.ext" WAVE (or other format)
    file_pattern = re.compile(r'^FILE\s+"([^"]+)"\s+', re.MULTILINE | re.IGNORECASE)
    
    for dirpath, dirnames, filenames in os.walk(root_path):
        # Find all CUE files in this directory
        cue_files = [f for f in filenames if f.lower().endswith(".cue")]
        
        if cue_files:
            rel_dir = os.path.relpath(dirpath, root_path) if dirpath != root_path else "."
            log_func(f"📁 Scanning directory: {rel_dir}")
        
        for cue_file in cue_files:
            cue_path = os.path.join(dirpath, cue_file)
            log_func(f"  📄 Found CUE file: {cue_file}")
            
            try:
                # Parse the CUE file using cueparser
                cue_sheet = cueparser.CueSheet()
                cue_sheet.setOutputFormat('', '')  # Set empty output formats
                
                with open(cue_path, 'r', encoding='utf-8', errors='ignore') as f:
                    cue_content = f.read()
                    cue_sheet.setData(cue_content)
                    cue_sheet.parse()
                
                # Extract FILE directives from the parsed data
                referenced_files = []
                for line in cue_sheet.data:
                    match = file_pattern.match(line)
                    if match:
                        referenced_files.append(match.group(1))
                
                if not referenced_files:
                    log_func(f"    ⚠️  No FILE directives found in {cue_file}")
                    continue
                
                log_func(f"    🔗 Found {len(referenced_files)} audio file reference(s) in CUE")
                
                # Check if we need to split the CUE file (multiple images)
                if len(referenced_files) > 1:
                    log_func(f"    🔪 Multi-image CUE detected! Creating separate CUE files...")
                    created_cues = _split_multi_image_cue(cue_path, referenced_files, log_func)
                    
                    # Now add pairs using the newly created CUE files
                    for new_cue_path, audio_file_name in created_cues:
                        # The file path in CUE is relative to the CUE file location
                        audio_file_path = os.path.join(dirpath, audio_file_name)
                        
                        if os.path.exists(audio_file_path):
                            pairs.append((new_cue_path, audio_file_path, dirpath))
                        # If not found directly, try case-insensitive search (for Linux compatibility)
                        else:
                            for existing_file in filenames:
                                if existing_file.lower() == audio_file_name.lower():
                                    audio_file_path = os.path.join(dirpath, existing_file)
                                    pairs.append((new_cue_path, audio_file_path, dirpath))
                                    break
                else:
                    # Single image CUE - use original logic
                    audio_file_name = referenced_files[0]
                    # The file path in CUE is relative to the CUE file location
                    audio_file_path = os.path.join(dirpath, audio_file_name)
                    
                    if os.path.exists(audio_file_path):
                        pairs.append((cue_path, audio_file_path, dirpath))
                        log_func(f"    ✅ Matched: {cue_file} → {audio_file_name}")
                    # If not found directly, try case-insensitive search (for Linux compatibility)
                    else:
                        found = False
                        for existing_file in filenames:
                            if existing_file.lower() == audio_file_name.lower():
                                audio_file_path = os.path.join(dirpath, existing_file)
                                pairs.append((cue_path, audio_file_path, dirpath))
                                log_func(f"    ✅ Matched (case-insensitive): {cue_file} → {existing_file}")
                                found = True
                                break
                        
                        if not found:
                            log_func(f"    ❌ Audio file not found: {audio_file_name}")
                            
            except Exception as e:
                log_func(f"    ⚠️  Error reading {cue_file}: {str(e)}")
                pass
    
    return pairs
