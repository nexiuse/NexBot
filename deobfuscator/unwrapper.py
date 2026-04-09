"""
Multi-layer unwrapper for obfuscated Lua scripts.
Handles: Base64, string.char, byte tables, XOR, loadstring wrapping.
"""

import re
import base64
import codecs
from typing import Optional, List, Tuple


MAX_LAYERS = 20  # Maximum recursion depth


def _try_base64_decode(encoded: str) -> Optional[str]:
    """Try to decode a base64 string."""
    # Clean up the string
    cleaned = encoded.strip().replace("\n", "").replace("\r", "").replace(" ", "")
    
    # Pad if necessary
    padding = 4 - len(cleaned) % 4
    if padding != 4:
        cleaned += "=" * padding
    
    try:
        decoded = base64.b64decode(cleaned).decode("utf-8", errors="replace")
        # Verify it looks like Lua code
        if any(kw in decoded for kw in ["local", "function", "end", "return", "if", "then", "else"]):
            return decoded
    except Exception:
        pass
    
    return None


def _extract_base64_loadstring(code: str) -> Optional[str]:
    """Extract and decode base64 from loadstring patterns."""
    
    # Pattern: loadstring(decode("BASE64"))()
    patterns = [
        # Generic: variable = "BASE64STRING"; loadstring(decode(variable))
        r'(?:local\s+)?(\w+)\s*=\s*["\']([A-Za-z0-9+/=\s]{40,})["\']',
        # Direct: loadstring(decode("BASE64"))
        r'loadstring\s*\(\s*(?:\w+\s*\(\s*)?["\']([A-Za-z0-9+/=\s]{40,})["\']',
        # HttpService:JSONDecode or base64 decode
        r'[Dd]ecode\s*\(\s*["\']([A-Za-z0-9+/=\s]{40,})["\']',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, code, re.DOTALL)
        for match in matches:
            # match could be tuple (from groups) or string
            b64str = match[-1] if isinstance(match, tuple) else match
            result = _try_base64_decode(b64str)
            if result:
                return result
    
    # Try the entire code as base64 (some scripts are just raw base64)
    if re.match(r'^[A-Za-z0-9+/=\s]+$', code.strip()):
        result = _try_base64_decode(code.strip())
        if result:
            return result
    
    return None


def _decode_string_char(code: str) -> Optional[str]:
    """Decode string.char(...) patterns."""
    
    # Find string.char(num, num, num, ...) patterns
    pattern = r'string\.char\s*\(\s*([\d\s,]+)\s*\)'
    matches = re.findall(pattern, code)
    
    if not matches:
        return None
    
    decoded_parts = []
    for match in matches:
        try:
            nums = [int(n.strip()) for n in match.split(",") if n.strip()]
            decoded_parts.append("".join(chr(n) for n in nums if 0 <= n <= 0x10FFFF))
        except (ValueError, OverflowError):
            continue
    
    if not decoded_parts:
        return None
    
    # If the decoded content looks like Lua code, return it
    full_decoded = "".join(decoded_parts)
    if len(full_decoded) > 20 and any(kw in full_decoded for kw in ["local", "function", "end", "return"]):
        return full_decoded
    
    # Otherwise, try to replace string.char calls in the code with their decoded values
    result = code
    for match in matches:
        try:
            nums = [int(n.strip()) for n in match.split(",") if n.strip()]
            decoded = "".join(chr(n) for n in nums if 0 <= n <= 0x10FFFF)
            original = f'string.char({match})'
            result = result.replace(original, f'"{decoded}"')
        except (ValueError, OverflowError):
            continue
    
    if result != code:
        return result
    
    return None


def _decode_byte_table(code: str) -> Optional[str]:
    """Decode byte table patterns like {104, 101, 108, 108, 111}."""
    
    # Find large number tables
    pattern = r'(?:local\s+\w+\s*=\s*)?\{\s*(\d+(?:\s*,\s*\d+){10,})\s*\}'
    matches = re.findall(pattern, code)
    
    for match in matches:
        try:
            nums = [int(n.strip()) for n in match.split(",") if n.strip()]
            # Check if values are in valid byte range
            if all(0 <= n <= 255 for n in nums):
                decoded = "".join(chr(n) for n in nums)
                if any(kw in decoded for kw in ["local", "function", "end", "return", "if"]):
                    return decoded
        except (ValueError, OverflowError):
            continue
    
    return None


def _decode_escaped_string(code: str) -> Optional[str]:
    """Decode \\DDD escape sequences in strings."""
    
    # Find strings with lots of escape sequences
    pattern = r'["\']((\\(\d{1,3}))+)["\']'
    matches = re.finditer(pattern, code)
    
    changes_made = False
    result = code
    
    for match in matches:
        full_escaped = match.group(1)
        nums = re.findall(r'\\(\d{1,3})', full_escaped)
        if len(nums) < 10:
            continue
        
        try:
            decoded = "".join(chr(int(n)) for n in nums if 0 <= int(n) <= 0x10FFFF)
            if any(kw in decoded for kw in ["local", "function", "end"]):
                original = match.group(0)
                result = result.replace(original, f'"{decoded}"')
                changes_made = True
        except (ValueError, OverflowError):
            continue
    
    if changes_made and any(kw in result for kw in ["local", "function", "end"]):
        return result
    
    return None


def _extract_loadstring_content(code: str) -> Optional[str]:
    """
    Extract the string argument from loadstring() calls.
    Handles: loadstring("code")(), loadstring('code')()
    """
    
    # Simple loadstring("content")
    patterns = [
        r'loadstring\s*\(\s*"((?:[^"\\]|\\.)*)"\s*\)',
        r"loadstring\s*\(\s*'((?:[^'\\]|\\.)*)'\s*\)",
        r'loadstring\s*\(\s*\[\[(.*?)\]\]\s*\)',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, code, re.DOTALL)
        for match in matches:
            # Unescape
            try:
                decoded = codecs.decode(match, 'unicode_escape')
            except Exception:
                decoded = match
            
            if len(decoded) > 20 and any(kw in decoded for kw in ["local", "function", "end"]):
                return decoded
    
    return None


def _decode_xor(code: str) -> Optional[str]:
    """Attempt to decode XOR-encrypted strings."""
    
    # Look for XOR decryption patterns
    # Common: for i=1,#str do result = result .. string.char(bit32.bxor(string.byte(str,i), key)) end
    xor_pattern = r'bit(?:32)?\.bxor\s*\(\s*string\.byte\s*\(\s*(\w+)\s*,\s*\w+\s*\)\s*,\s*(\d+)\s*\)'
    matches = re.findall(xor_pattern, code)
    
    if not matches:
        return None
    
    # Find the encrypted string variable
    for var_name, xor_key in matches:
        key = int(xor_key)
        # Find the variable value
        var_pattern = rf'(?:local\s+)?{re.escape(var_name)}\s*=\s*["\']([^"\']+)["\']'
        var_matches = re.findall(var_pattern, code)
        
        for encrypted in var_matches:
            try:
                decrypted = "".join(chr(ord(c) ^ key) for c in encrypted)
                if any(kw in decrypted for kw in ["local", "function", "end"]):
                    return decrypted
            except (ValueError, OverflowError):
                continue
    
    return None


def _extract_concatenated_strings(code: str) -> Optional[str]:
    """Extract and join string concatenation patterns."""
    
    # Pattern: "str1" .. "str2" .. "str3"
    concat_pattern = r'(?:["\']([^"\']*)["\'](?:\s*\.\.\s*)?){3,}'
    
    matches = re.finditer(concat_pattern, code)
    result = code
    changes_made = False
    
    for match in matches:
        full = match.group(0)
        parts = re.findall(r'["\']([^"\']*)["\']', full)
        if len(parts) >= 3:
            joined = "".join(parts)
            if len(joined) > 20:
                result = result.replace(full, f'"{joined}"')
                changes_made = True
    
    if changes_made:
        return result
    
    return None


def unwrap_single_layer(code: str) -> Tuple[Optional[str], str]:
    """
    Attempt to unwrap a single layer of obfuscation.
    
    Returns:
        Tuple of (unwrapped_code or None, method_used)
    """
    
    # Try each method in order of likelihood
    methods = [
        (_extract_base64_loadstring, "Base64 Decode"),
        (_extract_loadstring_content, "Loadstring Extract"),
        (_decode_string_char, "String.char Decode"),
        (_decode_byte_table, "Byte Table Decode"),
        (_decode_escaped_string, "Escape Sequence Decode"),
        (_decode_xor, "XOR Decrypt"),
        (_extract_concatenated_strings, "String Concat Resolve"),
    ]
    
    for method, name in methods:
        try:
            result = method(code)
            if result and result.strip() != code.strip():
                return result, name
        except Exception:
            continue
    
    return None, "None"


def unwrap_layers(code: str) -> Tuple[str, List[str]]:
    """
    Recursively unwrap all layers of obfuscation.
    
    Returns:
        Tuple of (final_code, list_of_methods_used)
    """
    methods_used = []
    current = code
    
    for i in range(MAX_LAYERS):
        result, method = unwrap_single_layer(current)
        
        if result is None:
            break
        
        methods_used.append(f"Layer {i+1}: {method}")
        current = result
    
    return current, methods_used
