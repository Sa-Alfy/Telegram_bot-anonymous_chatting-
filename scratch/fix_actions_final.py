
import os

file_path = "core/engine/actions.py"
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    if 'return {"success": code in {1, 2}, "state": msg, "version": ver}' in line and i > 420 and i < 440:
        indent = line[:line.find('return')]
        new_lines.append(f"{indent}code, msg, ver = await RedisScripts.execute(redis, RedisScripts.SET_STATE_LUA, keys, [uid, str(ts), new_s])\n")
        new_lines.append(line)
        continue
    new_lines.append(line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print("Restored logic successfully")
