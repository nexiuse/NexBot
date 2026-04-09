"""
Lua code beautifier / formatter.
Formats minified/ugly Lua code into readable format.
"""

import re


INDENT_KEYWORDS = {"function", "if", "for", "while", "repeat", "do"}
DEDENT_KEYWORDS = {"end", "until"}
MIDLINE_KEYWORDS = {"else", "elseif"}

LUA_KEYWORDS = {
    "and", "break", "do", "else", "elseif", "end",
    "false", "for", "function", "goto", "if", "in",
    "local", "nil", "not", "or", "repeat", "return",
    "then", "true", "until", "while"
}


def beautify_lua(code: str) -> str:
    """
    Format Lua code with proper indentation and line breaks.
    """
    if not code or not code.strip():
        return code
    
    # Step 1: Normalize line endings
    code = code.replace("\r\n", "\n").replace("\r", "\n")
    
    # Step 2: Add line breaks after semicolons (if not inside strings)
    code = _add_line_breaks(code)
    
    # Step 3: Apply indentation
    code = _indent_code(code)
    
    # Step 4: Clean up excessive blank lines
    code = re.sub(r'\n{3,}', '\n\n', code)
    
    # Step 5: Trim trailing whitespace on each line
    lines = [line.rstrip() for line in code.split("\n")]
    code = "\n".join(lines)
    
    return code.strip() + "\n"


def _add_line_breaks(code: str) -> str:
    """Add line breaks at logical points."""
    result = []
    in_string = False
    string_char = None
    in_long_string = False
    i = 0
    
    while i < len(code):
        char = code[i]
        
        # Handle long strings [[ ]]
        if not in_string and i + 1 < len(code) and code[i:i+2] == "[[":
            in_long_string = True
            result.append(char)
            i += 1
            continue
        
        if in_long_string and i + 1 < len(code) and code[i:i+2] == "]]":
            in_long_string = False
            result.append(char)
            i += 1
            result.append(code[i])
            i += 1
            continue
        
        if in_long_string:
            result.append(char)
            i += 1
            continue
        
        # Handle strings
        if char in ('"', "'") and not in_string:
            in_string = True
            string_char = char
            result.append(char)
            i += 1
            continue
        
        if in_string and char == string_char and (i == 0 or code[i-1] != "\\"):
            in_string = False
            result.append(char)
            i += 1
            continue
        
        if in_string:
            result.append(char)
            i += 1
            continue
        
        # Handle comments
        if i + 1 < len(code) and code[i:i+2] == "--":
            # Find end of line
            end = code.find("\n", i)
            if end == -1:
                result.append(code[i:])
                break
            result.append(code[i:end+1])
            i = end + 1
            continue
        
        # Add line break after semicolons
        if char == ";":
            result.append("\n")
            i += 1
            # Skip whitespace after semicolon
            while i < len(code) and code[i] in (" ", "\t"):
                i += 1
            continue
        
        result.append(char)
        i += 1
    
    code = "".join(result)
    
    # Add line breaks before keywords (if not already on new line)
    for kw in ["local ", "if ", "for ", "while ", "repeat ", "function ", "return ", "end", "else", "elseif"]:
        # Don't break inside strings
        code = re.sub(
            rf'(?<=[^\n\s])(\s+)({re.escape(kw)})',
            rf'\n\2',
            code
        )
    
    return code


def _indent_code(code: str) -> str:
    """Apply proper indentation to Lua code."""
    lines = code.split("\n")
    result = []
    indent = 0
    
    for line in lines:
        stripped = line.strip()
        
        if not stripped:
            result.append("")
            continue
        
        # Get the first word
        first_word = re.match(r'(\w+)', stripped)
        first_word = first_word.group(1) if first_word else ""
        
        # Check for dedent
        should_dedent = False
        if first_word in DEDENT_KEYWORDS:
            should_dedent = True
        elif first_word in MIDLINE_KEYWORDS:
            should_dedent = True
        
        if should_dedent and indent > 0:
            indent -= 1
        
        # Apply current indent
        result.append("    " * indent + stripped)
        
        # Check for indent increase
        should_indent = False
        
        # Count opening and closing keywords in line
        # Simple approach: check if line ends with 'then', 'do', etc.
        if first_word in MIDLINE_KEYWORDS:
            should_indent = True
        elif re.search(r'\bthen\s*$', stripped):
            should_indent = True
        elif re.search(r'\bdo\s*$', stripped):
            should_indent = True
        elif re.search(r'\brepeat\s*$', stripped):
            should_indent = True
        elif re.match(r'^(?:local\s+)?function\s+', stripped) and not re.search(r'\bend\s*$', stripped):
            should_indent = True
        elif re.search(r'function\s*\([^)]*\)\s*$', stripped) and not re.search(r'\bend\s*[\)\s]*$', stripped):
            should_indent = True
        elif re.search(r'\belse\s*$', stripped):
            should_indent = True
        
        # Don't indent if line also has 'end' (single-line blocks)
        if should_indent and re.search(r'\bend\b', stripped) and first_word not in MIDLINE_KEYWORDS:
            # Check if it's truly single-line (end matches the opening)
            opens = len(re.findall(r'\b(?:function|if|for|while|do|repeat)\b', stripped))
            closes = len(re.findall(r'\bend\b', stripped))
            if opens <= closes:
                should_indent = False
        
        if should_indent:
            indent += 1
    
    return "\n".join(result)


def minify_stats(original: str, beautified: str) -> str:
    """Generate stats about the beautification."""
    orig_lines = len(original.split("\n"))
    new_lines = len(beautified.split("\n"))
    orig_chars = len(original)
    new_chars = len(beautified)
    
    return (
        f"📊 **Stats:**\n"
        f"• Lines: {orig_lines} → {new_lines}\n"
        f"• Characters: {orig_chars:,} → {new_chars:,}"
    )
