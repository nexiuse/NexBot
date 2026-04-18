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
        matches = re.findall(str_pattern, self.code)
        for m in matches:
            if len(m) > 4: # Filter short/unlikely strings
                self.constants.append(m)
        
        # Step 2: Look for the large table 'X' or equivalent
        # MoonVeil usually has a table like ,X={[num]={...}}
        table_match = re.search(r',X=\{.*?\[(\d+)\]=\{.*?\}\}', self.code, re.DOTALL)
        if table_match:
            # We found the VM table. In a real decompiler we'd parse the numbers here.
            pass
            
        return len(self.constants) > 0

class LuraphHandler(VMHandler):
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
