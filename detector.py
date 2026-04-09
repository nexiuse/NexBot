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
            r'\\(\d{1,3})',
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
    "moonsec_v1": {
        "patterns": [
            r'MoonSec\s*V?\d',
            r'local\s+\w+\s*=\s*string\.byte\s*;',
            r'local\s+\w+,\s*\w+,\s*\w+,\s*\w+\s*=\s*string\.byte\s*,\s*string\.char\s*,\s*string\.sub\s*,\s*string\.gsub',
            r'getfenv\s*\(\s*\)\s*\[',
        ],
        "name": "MoonSec",
        "difficulty": "hard",
    },
    "ironbrew": {
        "patterns": [
            r'IronBrew',
            r'local\s+\w+\s*=\s*bit(?:32)?\.(?:band|bor|bxor|bnot)',
            r'local\s+\w+\s*=\s*{\s*\[\d+\]\s*=\s*function',
        ],
        "name": "IronBrew",
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
    
    # Sort by score, prioritize harder obfuscators on tie
    difficulty_weight = {"hard": 3, "medium": 2, "easy": 1, "trivial": 0}
    best = max(scores.keys(), key=lambda k: (
        scores[k],
        difficulty_weight.get(SIGNATURES[k]["difficulty"], 0)
    ))
    
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
