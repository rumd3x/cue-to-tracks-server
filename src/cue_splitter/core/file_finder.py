"""File discovery and searching utilities"""
import os


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
                    # Skip images with back, side, or inner
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
    
    Handles cases where CUE files include the image extension in their name:
    - Normal: "album.cue" + "album.flac"
    - With extension: "album.flac.cue" + "album.flac"
    
    Args:
        root_path: Root directory to search
        
    Returns:
        List of tuples: [(cue_path, image_path, containing_dir), ...]
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
            
            # Strategy 1: Direct match (base_name + image_extension)
            # Works for: "album.cue" + "album.flac"
            for ext in image_extensions:
                candidate = os.path.join(dirpath, base_name + ext)
                if os.path.exists(candidate):
                    image_file = candidate
                    break
            
            # Strategy 2: If base_name already ends with an image extension,
            # the image file might be the base_name itself
            # Works for: "album.flac.cue" + "album.flac"
            if not image_file:
                base_name_lower = base_name.lower()
                for ext in image_extensions:
                    if base_name_lower.endswith(ext):
                        candidate = os.path.join(dirpath, base_name)
                        if os.path.exists(candidate):
                            image_file = candidate
                            break
            
            if image_file:
                pairs.append((cue_path, image_file, dirpath))
    
    return pairs
