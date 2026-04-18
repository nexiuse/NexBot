"""
Obfuscator type detector.
Analyzes Lua code patterns to identify which obfuscator was used.
"""

import re
from typing import Tuple

# Obfuscator signatures
SIGNATURES = {
    "base64_loadstring": {
        "patterns": [
            r'loadstring\s*\(\s*(?:game:GetService\(["\']HttpService["\']\):)?(?:base64)?[Dd]ecode',
            r'local\s+\w+\s*=\s*["\'][A-Za-z0-9+/=]{50,}["\']',
            r'loadstring\s*\(\s*(?:decode|dec|b64)\s*\(',
        ],
        "name": "Base64 Loadstring",
        "difficulty": "easy",
    },
    "string_char": {
        "patterns": [
            r'string\.char\s*\(\s*\d+(?:\s*,\s*\d+){10,}\s*\)',
            r'(?:\\\d{1,3}){20,}', # At least 20 escaped decimals in a row
            r'table\.concat\s*\(\s*\{[^}]*string\.char',
        ],
        "name": "String.char Encoding",
        "difficulty": "easy",
    },
    "byte_table": {
        "patterns": [
            r'local\s+\w+\s*=\s*\{\s*\d+\s*(?:,\s*\d+\s*){20,}\}',
            r'for\s+\w+\s*,\s*\w+\s+in\s+(?:ipairs|pairs)\s*\(\s*\w+\s*\)\s+do\s+\w+\s*=\s*\w+\s*\.\.\s*string\.char',
        ],
        "name": "Byte Table",
        "difficulty": "easy",
    },
    "xor_function_calls": {
        "patterns": [
            r'local\s+\w+\s*=\s*string\.char\s*\n\s*local\s+\w+\s*=\s*string\.byte',
            r'local\s+\w+\s*=\s*string\.byte\s*;?\s*local\s+\w+\s*=\s*string\.char',
            r'bit(?:32)?\s+or\s+bit\b',
            r'table\.concat\s*\(\s*\w+\s*\)\s*\n\s*end',
            r'\w+\s*\(\s*"(?:\\[0-9]{1,3})+[^"]*"\s*,\s*"(?:\\[0-9]{1,3})+[^"]*"\s*\)',
        ],
        "name": "XOR Function Calls (Cyclic Key)",
        "difficulty": "medium",
    },
    "xor_cipher": {
        "patterns": [
            r'bit(?:32)?\.bxor\s*\(',
            r'local\s+function\s+\w+\s*\(\s*\w+\s*,\s*\w+\s*\).*bit.*xor',
        ],
        "name": "XOR Cipher",
        "difficulty": "medium",
    },
    "loadstring_wrapper": {
        "patterns": [
            r'loadstring\s*\(\s*["\']',
            r'load\s*\(\s*function\s*\(\s*\)',
            r'loadstring\s*\(\s*\(\s*function\s*\(',
        ],
        "name": "Loadstring Wrapper",
        "difficulty": "easy",
    },
    "wearedevs": {
        "patterns": [
            r'WeAreDevs',
            r'_G\["\w+"\]\s*=\s*loadstring',
            r'local\s+\w+\s*=\s*{}\s*;\s*local\s+\w+\s*=\s*"',
            r'HttpGet\s*\(\s*["\']https?://cdn\.wearedevs\.net',
        ],
        "name": "WeAreDevs",
        "difficulty": "medium",
    },
    "moonveil": {
        "patterns": [
            r'MoonVeil\s*Obfuscator',
            r'moonveil\.cc',
            r'local\s+\w+\s*=\s*bit32\.bxor\s*,\s*getmetatable',
            r'repeat\s*if\s*\w+\s*>=\s*\d+\s*then',
        ],
        "name": "MoonVeil",
        "difficulty": "hard",
    },
    "luraph": {
        "patterns": [
            r'LPH_',
            r'LURAPH',
            r'local\s+\w+\s*=\s*\w+\[\d+\]\s*;\s*local\s+\w+\s*=\s*\w+\[\d+\]',
            r'while\s*true\s*do\s*local\s+\w+\s*=\s*\w+\[\w+\]\s*if\s*\w+\s*==\s*\d+\s*then',
        ],
        "name": "Luraph",
        "difficulty": "hard",
    },
    "beautify_only": {
        "patterns": [
            r'local\s+\w+\s*=\s*\w+',
        ],
        "name": "Minified/Uglified (not obfuscated)",
        "difficulty": "trivial",
    },
}


def detect_obfuscator(code: str) -> Tuple[str, str, str]:
    """
    Detect the obfuscator used on a Lua script.
    
    Returns:
        Tuple of (obfuscator_key, obfuscator_name, difficulty)
    """
    scores = {}
    
    for key, sig in SIGNATURES.items():
        score = 0
        for pattern in sig["patterns"]:
            matches = re.findall(pattern, code, re.IGNORECASE | re.DOTALL)
            score += len(matches)
        if score > 0:
            scores[key] = score
    
    if not scores:
        return "unknown", "Unknown Obfuscator", "unknown"
    
    # Sort by score, but give a massive boost to "hard" signatures
    # and a tie-breaker based on difficulty weight
    difficulty_weight = {"hard": 10000, "medium": 100, "easy": 1, "trivial": 0}
    
    def calculate_rank(k):
        base_score = scores[k]
        # If it's a hard/medium obfuscator and we have at least one match,
        # we give it a significant weight to avoid being drowned by easy patterns.
        weight = difficulty_weight.get(SIGNATURES[k]["difficulty"], 0)
        return (weight if base_score > 0 else 0) + base_score

    best = max(scores.keys(), key=calculate_rank)
    
    sig = SIGNATURES[best]
    return best, sig["name"], sig["difficulty"]


def get_detection_report(code: str) -> str:
    """Generate a human-readable detection report."""
    key, name, difficulty = detect_obfuscator(code)
    
    difficulty_emoji = {
        "trivial": "🟢",
        "easy": "🟢",
        "medium": "🟡",
        "hard": "🔴",
        "unknown": "⚪",
    }
    
    emoji = difficulty_emoji.get(difficulty, "⚪")
    
    lines = [
        f"**Obfuscator Terdeteksi:** {name}",
        f"**Tingkat Kesulitan:** {emoji} {difficulty.upper()}",
    ]
    
    if difficulty == "hard":
        lines.append("⚠️ *Obfuscator ini menggunakan VM bytecode. Deobfuscation terbatas pada string extraction.*")
    
    return "\n".join(lines)
