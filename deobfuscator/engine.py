"""
Main deobfuscation engine.
Orchestrates detection, unwrapping, and beautification.
"""

import time
from typing import Optional
from .detector import detect_obfuscator, get_detection_report
from .unwrapper import unwrap_layers
from .beautifier import beautify_lua, minify_stats
from .lifter import VMLifter


class DeobfuscationResult:
    """Holds the result of a deobfuscation attempt."""
    
    def __init__(self):
        self.success: bool = False
        self.original_code: str = ""
        self.deobfuscated_code: str = ""
        self.obfuscator_key: str = ""
        self.obfuscator_name: str = ""
        self.difficulty: str = ""
        self.layers_unwrapped: list = []
        self.beautified: bool = False
        self.error: Optional[str] = None
        self.time_taken: float = 0.0
    
    def generate_report(self) -> str:
        """Generate a Discord-friendly report."""
        lines = ["## 🔓 NexHub Deobfuscator - Report\n"]
        
        # Detection
        difficulty_emoji = {
            "trivial": "🟢", "easy": "🟢",
            "medium": "🟡", "hard": "🔴", "unknown": "⚪"
        }
        emoji = difficulty_emoji.get(self.difficulty, "⚪")
        lines.append(f"**Obfuscator:** {self.obfuscator_name}")
        lines.append(f"**Kesulitan:** {emoji} {self.difficulty.upper()}")
        lines.append(f"**Waktu:** {self.time_taken:.2f}s")
        lines.append("")
        
        # Layers
        if self.layers_unwrapped:
            lines.append("**Layers yang di-unwrap:**")
            for layer in self.layers_unwrapped:
                lines.append(f"  ✅ {layer}")
            lines.append("")
        
        # Stats
        if self.deobfuscated_code:
            orig_size = len(self.original_code)
            deob_size = len(self.deobfuscated_code)
            lines.append(f"**Ukuran:** {orig_size:,} → {deob_size:,} chars")
            
            if self.beautified:
                lines.append("**Format:** ✨ Beautified")
        
        # Status
        if self.success:
            lines.append("\n✅ **Deobfuscation berhasil!**")
        elif self.error:
            lines.append(f"\n❌ **Error:** {self.error}")
        else:
            lines.append("\n⚠️ **Tidak bisa sepenuhnya deobfuscate.** Obfuscator terlalu kompleks.")
        
        return "\n".join(lines)


class DeobfuscationEngine:
    """Main engine for deobfuscating Lua scripts."""
    
    def process(self, code: str, beautify: bool = True) -> DeobfuscationResult:
        """
        Process a Lua script through the full deobfuscation pipeline.
        
        Args:
            code: The obfuscated Lua code
            beautify: Whether to beautify the output
            
        Returns:
            DeobfuscationResult with all details
        """
        result = DeobfuscationResult()
        result.original_code = code
        start_time = time.time()
        
        try:
            # Step 1: Detect obfuscator
            key, name, difficulty = detect_obfuscator(code)
            result.obfuscator_key = key
            result.obfuscator_name = name
            result.difficulty = difficulty
            
            # Step 2: Unwrap layers
            unwrapped, methods = unwrap_layers(code)
            result.layers_unwrapped = methods
            
            # Initial assignment
            result.deobfuscated_code = unwrapped
            
            # Step 3: VM Lifting (for hard obfuscators)
            # We do this BEFORE beautification to get the cleanest logic reconstruction
            if difficulty == "hard":
                lifter = VMLifter()
                lifted_code = lifter.process(unwrapped, key)
                if lifted_code != unwrapped:
                    result.deobfuscated_code = lifted_code
                    result.success = True
                    result.layers_unwrapped.append(f"Logic Restored: {key.upper()} instructions lifted")
            
            # Check if we actually deobfuscated anything beyond initial wrapping
            if result.deobfuscated_code.strip() != code.strip() or len(result.layers_unwrapped) > 0:
                result.success = True
            
            # Step 4: Beautify final result
            if beautify:
                result.deobfuscated_code = beautify_lua(result.deobfuscated_code)
                result.beautified = True
            
            # Extra fallback for hard obfuscators if lifting returned nothing new
            if difficulty == "hard" and not result.success:
                strings = self._extract_strings(code)
                if strings:
                    header = f"-- ⚠️ {name} detected - VM bytecode obfuscation\n"
                    header += f"-- Full deobfuscation not possible\n"
                    header += f"-- Extracted {len(strings)} readable strings:\n\n"
                    
                    string_section = "\n".join(
                        f'-- String {i+1}: "{s}"' for i, s in enumerate(strings[:100])
                    )
                    
                    result.deobfuscated_code = header + string_section
                    result.success = True  # Partial success
                    result.layers_unwrapped.append(f"String Extraction: {len(strings)} strings found")
        
        except Exception as e:
            result.error = str(e)
            result.success = False
        
        result.time_taken = time.time() - start_time
        return result
    
    def _extract_strings(self, code: str) -> list:
        """Extract all readable strings from obfuscated code."""
        import re
        
        strings = set()
        
        # Find all string literals
        for match in re.finditer(r'"([^"\\]*(?:\\.[^"\\]*)*)"', code):
            s = match.group(1)
            # Filter: only keep readable strings > 3 chars
            if len(s) > 3 and all(32 <= ord(c) <= 126 for c in s):
                strings.add(s)
        
        for match in re.finditer(r"'([^'\\]*(?:\\.[^'\\]*)*)'", code):
            s = match.group(1)
            if len(s) > 3 and all(32 <= ord(c) <= 126 for c in s):
                strings.add(s)
        
        # Sort by length (longer = more useful)
        return sorted(strings, key=len, reverse=True)
