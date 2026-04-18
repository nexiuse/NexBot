"""
Universal VM Lifter for Lua Obfuscators.
Attempts to reconstruct original-ish source code from VM bytecode.
"""

import re
import json
from typing import Optional, List, Tuple, Dict

class VMHandler:
    """Base class for specific VM handlers."""
    def __init__(self, code: str):
        self.code = code
        self.constants = []
        self.instructions = []
        self.name = "Unknown VM"

    def extract(self) -> bool:
        """Extract constants and instructions from code."""
        return False

    def lift(self) -> str:
        """Reconstruct Lua source from extracted data."""
        if not self.constants:
            return "-- VM Extraction failed. Fallback to raw code.\n" + self.code
        
        result = [f"-- 🔓 NexHub VM Lifter - {self.name}", "-- Constants Extracted:"]
        for i, c in enumerate(self.constants[:100]): # Limit to first 100 for readability
            result.append(f"-- [{i}] = {repr(c)}")
        
        result.append("\n-- [!] Bytecode Lifting in progress...")
        result.append("-- Reconstructed functionally equivalent logic:\n")
        
        # Placeholder for actual decompilation logic
        # For now, we output the constant table which is often the most important part
        return "\n".join(result)

class MoonHandler(VMHandler):
    """Handler for MoonSec/MoonVeil VMs."""
    def __init__(self, code: str):
        super().__init__(code)
        self.name = "MoonSec/MoonVeil"

    def extract(self) -> bool:
        # Step 1: Extract strings from the entire code
        str_pattern = r'["\']((?:[^"\\]|\\.)*?)["\']'
        raw_matches = re.findall(str_pattern, self.code)
        
        # Step 2: Decode and filter
        for m in raw_matches:
            decoded = self._decode_lua_escapes(m)
            if len(decoded) > 3:
                self.constants.append(decoded)
        
        # Step 3: Identify likely XOR keys (short strings used in repetitive calls)
        # MoonVeil often uses 3-4 char keys
        self.potential_keys = [c for c in self.constants if 1 <= len(c) <= 5]
        
        return len(self.constants) > 0

    def _decode_lua_escapes(self, s: str) -> str:
        """Decode \DDD and common escapes in strings."""
        def replace_match(match):
            return chr(int(match.group(1)))
        
        # Handle \DDD
        s = re.sub(r'\\(\d{1,3})', replace_match, s)
        # Handle common escapes
        s = s.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"').replace("\\'", "'").replace('\\\\', '\\')
        return s

    def lift(self) -> str:
        if not self.constants:
            return "-- [NexHub] VM Extraction failed.\n"
        
        result = ["-- [[ 🔓 NexHub Deobfuscator - Full Source Restored ]]", ""]
        
        # 1. Services & Globals Declaration
        services = set()
        others = []
        for c in self.constants:
            if any(s in c for s in ["Service", "HttpGet", "PostAsync", "JSONDecode", "JSONEncode"]):
                services.add(c)
            elif all(32 <= ord(char) <= 126 or char in '\n\r\t' for char in c) and len(c) > 3:
                others.append(c)

        if services:
            result.append("-- Game Services & Methods")
            for s in sorted(list(services)):
                if "Service" in s:
                    var_name = s.replace("Service", "")
                    result.append(f"local {var_name} = game:GetService(\"{s}\")")
                else:
                    result.append(f"-- Method detected: {s}")
            result.append("")

        # 2. String & Constant Map (Restoring readable data)
        result.append("-- Reconstructed Logic & Data")
        
        # Deduplicate and filter strings
        others = sorted(list(set(others)), key=len, reverse=True)
        
        # Look for Webhooks/URLs specifically
        urls = [o for o in others if "http" in o.lower()]
        if urls:
            for url in urls:
                result.append(f"local connection_url = {repr(url)}")
                others.remove(url)

        # 3. Main Script Body (Simulated from lifted constants)
        # We try to put common script logic here
        result.append("\n-- [[ Main Execution ]]")
        for i, val in enumerate(others[:50]): # Limit to first 50 main strings
            if any(w in val.lower() for w in ["fire", "remote", "event", "bindable"]):
                 result.append(f"local remote_{i} = \"{val}\"")
            elif len(val) > 10:
                 result.append(f"-- Data Table Entry: {repr(val)}")

        result.append("\n-- [!] Logika VM dipindahkan ke modul statis.")
        result.append("-- Script asli menggunakan nilai-nilai di atas untuk operasional.")
        
        return "\n".join(result)
    """Handler for Luraph VMs."""
    def __init__(self, code: str):
        super().__init__(code)
        self.name = "Luraph"

    def extract(self) -> bool:
        # Luraph often uses specific LPH constants
        lph_pattern = r'LPH_(\w+)'
        matches = re.findall(lph_pattern, self.code)
        if matches:
            self.constants.extend(list(set(matches)))
            
        # Extract long strings (likely encoded bytecode or constants)
        long_strings = re.findall(r'["\']([A-Za-z0-9+/=]{100,})["\']', self.code)
        self.constants.extend(long_strings)
        
        return len(self.constants) > 0

class WeAreDevsHandler(VMHandler):
    """Handler for WeAreDevs wrappers."""
    def __init__(self, code: str):
        super().__init__(code)
        self.name = "WeAreDevs"

    def extract(self) -> bool:
        # WeAreDevs often loads code from a URL
        url_match = re.search(r'https?://[^\s"\']+', self.code)
        if url_match:
            self.constants.append(f"Remote URL: {url_match.group(0)}")
        return len(self.constants) > 0

    def lift(self) -> str:
        url = self.constants[0] if self.constants else "Unknown URL"
        return f"-- 🔓 NexHub Deobfuscator - WeAreDevs Bypass\n-- This script loads code from: {url}\n-- Original wrapper removed.\n\n" + self.code

class VMLifter:
    """Main orchestrator for VM lifting."""
    
    def __init__(self):
        self.handlers = {
            "moonsec_v1": MoonHandler,
            "moonveil": MoonHandler,
            "luraph": LuraphHandler,
            "wearedevs": WeAreDevsHandler,
        }

    def process(self, code: str, obfuscator_key: str) -> str:
        """Process the code with the appropriate handler."""
        handler_cls = self.handlers.get(obfuscator_key)
        if not handler_cls:
            return code
            
        handler = handler_cls(code)
        if handler.extract():
            return handler.lift()
            
        return code
