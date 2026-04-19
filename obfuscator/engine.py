import base64
import os
import binascii

class ObfuscatorEngine:
    def obfuscate_b64(self, code: str) -> str:
        code_bytes = code.encode("utf-8")
        b64_str = base64.b64encode(code_bytes).decode("utf-8")
        
        lua_template = f"""local b64 = "{b64_str}"
local decoded = nil
if game and game.HttpGet then
    local ok, result = pcall(function()
        return game:HttpGet("data:text/plain;base64," .. b64)
    end)
    if ok then decoded = result end
end
if not decoded then
    local alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    local lookup = {{}}
    for i = 1, #alphabet do lookup[alphabet:sub(i,i)] = i - 1 end
    local out = {{}}
    local val, bits = 0, 0
    for i = 1, #b64 do
        local c = b64:sub(i,i)
        if c == "=" then break end
        if lookup[c] then
            val = val * 64 + lookup[c]
            bits = bits + 6
            if bits >= 8 then
                bits = bits - 8
                local byte = math.floor(val / (2 ^ bits)) % 256
                table.insert(out, string.char(byte))
                val = val % (2 ^ bits)
            end
        end
    end
    decoded = table.concat(out)
end
loadstring(decoded)()"""
        return lua_template

    def obfuscate_xor(self, code: str) -> str:
        key = os.urandom(8)
        byte_code = code.encode("utf-8")
        result = bytearray()
        for i in range(len(byte_code)):
            result.append(byte_code[i] ^ key[i % len(key)])
        
        hex_str = binascii.hexlify(result).decode("utf-8")
        key_hex = binascii.hexlify(key).decode("utf-8")
        
        lua_template = f"""local xor_data = "{hex_str}"
local k = "{key_hex}"
local r = ""
local function h2b(h) return tonumber(h, 16) end
for i = 1, #xor_data, 2 do
    local b = h2b(xor_data:sub(i, i+1))
    local ki = ((i-1)/2) % (#k/2)
    local kb = h2b(k:sub(ki*2+1, ki*2+2))
    local dx
    if bit32 and bit32.bxor then
        dx = bit32.bxor(b, kb)
    elseif bit and bit.bxor then
        dx = bit.bxor(b, kb)
    else
        local res = 0
        local _b, _kb = b, kb
        local mult = 1
        for j = 1, 8 do
            local mb, mk = _b % 2, _kb % 2
            if mb ~= mk then res = res + mult end
            _b = math.floor(_b/2)
            _kb = math.floor(_kb/2)
            mult = mult * 2
        end
        dx = res
    end
    r = r .. string.char(dx)
end
loadstring(r)()"""
        return lua_template
