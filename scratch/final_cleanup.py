
import os

file_path = "core/engine/actions.py"
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip = 0
for i, line in enumerate(lines):
    if skip > 0:
        skip -= 1
        continue
    
    if 'data={"action": etype, "result_state": result.get("state")}' in line:
        new_lines.append('            return {"success": code in {1, 2}, "state": msg, "version": ver}\n')
        # We need to skip the next two lines: '        )' and '        return result'
        skip = 2 
        continue
    new_lines.append(line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print("Fixed successfully")
