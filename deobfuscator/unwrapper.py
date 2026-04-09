"""
Multi-layer unwrapper for obfuscated Lua scripts.
Handles: Base64, string.char, byte tables, XOR, loadstring wrapping,
         XOR function call resolution.
"""

import re
import base64
import codecs
from typing import Optional, List, Tuple
from collections import Counter


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
        r"loadstring\s*\(\s*'((?:[^'\\]|\\.)*)'\\s*\)",
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
    """Attempt to decode XOR-encrypted strings (simple single-key variant)."""
    
    # Look for XOR decryption patterns
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


# ═══════════════════════════════════════════════════════════════
# XOR FUNCTION CALL RESOLVER
# Handles patterns like: v7("\250\230\226", "\126\177\163")
# where v7 is a XOR decrypt function using cyclic key
# ═══════════════════════════════════════════════════════════════

def _parse_lua_escape_string(s: str) -> bytes:
    """
    Parse Lua string with \\DDD escape sequences into raw bytes.
    Handles: \\DDD (decimal), \\n, \\t, \\\\, \\", \\'
    """
    result = []
    i = 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            next_char = s[i + 1]
            # Numeric escape: \DDD (1-3 decimal digits)
            if next_char.isdigit():
                num_str = ''
                j = i + 1
                while j < len(s) and j < i + 4 and s[j].isdigit():
                    num_str += s[j]
                    j += 1
                val = int(num_str)
                result.append(val % 256)
                i = j
            elif next_char == 'n':
                result.append(10)
                i += 2
            elif next_char == 't':
                result.append(9)
                i += 2
            elif next_char == 'r':
                result.append(13)
                i += 2
            elif next_char == '\\':
                result.append(92)
                i += 2
            elif next_char == '"':
                result.append(34)
                i += 2
            elif next_char == "'":
                result.append(39)
                i += 2
            elif next_char == '0':
                result.append(0)
                i += 2
            elif next_char == 'a':
                result.append(7)
                i += 2
            elif next_char == 'b':
                result.append(8)
                i += 2
            elif next_char == 'f':
                result.append(12)
                i += 2
            elif next_char == 'v':
                result.append(11)
                i += 2
            else:
                # Unknown escape, keep as-is
                result.append(ord(s[i]))
                i += 1
        else:
            result.append(ord(s[i]))
            i += 1
    return bytes(result)


def _xor_decrypt_lua(encrypted: bytes, key: bytes) -> str:
    """
    XOR decrypt using Lua-style cyclic key.
    Lua code: string.char(bit32.bxor(string.byte(str, i), string.byte(key, 1 + (i % #key))) % 256)
    Note: Lua is 1-indexed, so i goes from 1 to #str
    """
    if len(key) == 0:
        return ""
    
    result = []
    key_len = len(key)
    for i in range(len(encrypted)):
        # Lua: v145 = i+1 (1-indexed), key_index = 1 + ((i+1) % key_len) → 0-indexed: (i+1) % key_len
        key_idx = (i + 1) % key_len
        decrypted_byte = (encrypted[i] ^ key[key_idx]) % 256
        result.append(chr(decrypted_byte))
    return "".join(result)


def _resolve_xor_function_calls(code: str) -> Optional[str]:
    """
    Detect XOR decrypt function and resolve ALL calls with decoded strings.
    
    Detects patterns like:
        local function v7(a, b)
            local t = {}
            for i = 1, #a do
                table.insert(t, string.char(bit32.bxor(string.byte(string.sub(a,i,i+1)), 
                    string.byte(string.sub(b, 1+(i%#b), 1+(i%#b)+1))) % 256))
            end
            return table.concat(t)
        end
    
    Then resolves: v7("\\250\\230", "\\126\\177") → decoded literal string
    """
    
    # Step 1: Find all function calls with two quoted string arguments
    # Pattern matches: funcname("escaped_str", "escaped_str")
    call_pattern = r'(\w+)\s*\(\s*"((?:[^"\\]|\\.)*)"\s*,\s*"((?:[^"\\]|\\.)*)"\s*\)'
    
    all_calls = re.findall(call_pattern, code)
    
    if len(all_calls) < 5:
        return None
    
    # Step 2: Find the most frequently called function with two string args
    func_counts = Counter(c[0] for c in all_calls)
    most_common = func_counts.most_common(1)
    
    if not most_common or most_common[0][1] < 5:
        return None
    
    xor_func_name = most_common[0][0]
    call_count = most_common[0][1]
    
    # Step 3: Verify this is likely an XOR function by checking that
    # arguments contain escape sequences (non-ASCII bytes)
    escape_calls = 0
    for fname, arg1, arg2 in all_calls:
        if fname == xor_func_name:
            if '\\' in arg1 or '\\' in arg2:
                escape_calls += 1
    
    # At least 50% of calls should have escape sequences
    if escape_calls < call_count * 0.3:
        return None
    
    # Step 4: Resolve all calls
    result = code
    changes = 0
    
    # Use re.finditer for positional replacement to avoid double-replacing
    pattern = re.compile(
        rf'{re.escape(xor_func_name)}\s*\(\s*"((?:[^"\\]|\\.)*)"\s*,\s*"((?:[^"\\]|\\.)*)"\s*\)'
    )
    
    # Collect all replacements first, then apply in reverse order
    replacements = []
    
    for match in pattern.finditer(code):
        encrypted_raw = match.group(1)
        key_raw = match.group(2)
        
        try:
            encrypted_bytes = _parse_lua_escape_string(encrypted_raw)
            key_bytes = _parse_lua_escape_string(key_raw)
            
            if len(key_bytes) == 0 or len(encrypted_bytes) == 0:
                continue
            
            decrypted = _xor_decrypt_lua(encrypted_bytes, key_bytes)
            
            # Only accept if result is mostly printable ASCII
            printable_count = sum(1 for c in decrypted if 32 <= ord(c) <= 126 or c in '\n\r\t')
            if len(decrypted) > 0 and printable_count / len(decrypted) >= 0.8:
                # Escape for Lua string
                lua_escaped = (decrypted
                    .replace('\\', '\\\\')
                    .replace('"', '\\"')
                    .replace('\n', '\\n')
                    .replace('\r', '\\r')
                    .replace('\t', '\\t')
                    .replace('\0', '\\0'))
                
                replacements.append((match.start(), match.end(), f'"{lua_escaped}"'))
                changes += 1
        except Exception:
            continue
    
    if changes == 0:
        return None
    
    # Apply replacements in reverse order to preserve positions
    for start, end, replacement in reversed(replacements):
        result = result[:start] + replacement + result[end:]
    
    return result


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
        (_resolve_xor_function_calls, "XOR Function Resolve"),
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

