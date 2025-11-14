"""Encoding detection and conversion utilities"""
import os
import chardet


def ensure_utf8_cue(cue_path, log_func):
    """
    Ensure CUE file is in UTF-8 encoding. If not, create a temporary UTF-8 version.
    
    Args:
        cue_path: Path to the CUE file
        log_func: Function to call for logging messages
        
    Returns:
        Tuple of (path_to_utf8_cue, is_temporary)
    """
    try:
        # Detect encoding
        with open(cue_path, 'rb') as f:
            raw_data = f.read()
            result = chardet.detect(raw_data)
            if result is None:
                log_func(f"⚠️ Could not detect encoding, using original file")
                return cue_path, False
                
            detected_encoding = result.get('encoding')
            confidence = result.get('confidence', 0)
        
        if not detected_encoding:
            log_func(f"⚠️ Could not detect encoding, using original file")
            return cue_path, False
            
        log_func(f"📝 CUE file encoding detected: {detected_encoding} (confidence: {confidence:.2%})")
        
        # If already UTF-8, no conversion needed
        if detected_encoding.upper() in ('UTF-8', 'ASCII'):
            log_func(f"✅ CUE file is already {detected_encoding}, no conversion needed")
            return cue_path, False
        
        # Convert to UTF-8
        log_func(f"🔄 Converting CUE file from {detected_encoding} to UTF-8...")
        temp_cue = cue_path + '.utf8.cue'
        
        # Read with detected encoding
        with open(cue_path, 'r', encoding=detected_encoding) as f:
            content = f.read()
        
        # Write as UTF-8
        with open(temp_cue, 'w', encoding='utf-8') as f:
            f.write(content)
        
        log_func(f"✅ Created UTF-8 CUE file: {os.path.basename(temp_cue)}")
        return temp_cue, True
        
    except Exception as e:
        log_func(f"⚠️ Failed to detect/convert CUE encoding: {e}")
        log_func(f"ℹ️ Using original CUE file as-is")
        return cue_path, False
