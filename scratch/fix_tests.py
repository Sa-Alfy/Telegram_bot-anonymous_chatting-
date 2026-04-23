
import os

file_path = "tests/test_cross_platform_chat.py"
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip = 0
for i, line in enumerate(lines):
    if skip > 0:
        skip -= 1
        continue
    
    # Check for report test
    if "match_state.active_chats[vid] = partner_id" in line and i > 890 and i < 910:
        new_lines.append("        # Set active chat authoritatively\n")
        new_lines.append("        await match_state.set_partner(vid, partner_id)\n")
        new_lines.append("        await match_state.set_partner(partner_id, vid)\n")
        new_lines.append("        await match_state.set_user_state(vid, UnifiedState.CHAT_ACTIVE)\n")
        new_lines.append("        await match_state.set_user_state(partner_id, UnifiedState.CHAT_ACTIVE)\n")
        # Check if next line is also active_chats
        if "match_state.active_chats[partner_id] = vid" in lines[i+1]:
            skip = 1
        continue

    # Check for block test
    if "match_state.active_chats[vid] = partner_id" in line and i > 920 and i < 940:
        new_lines.append("        # Set active chat authoritatively\n")
        new_lines.append("        await match_state.set_partner(vid, partner_id)\n")
        new_lines.append("        await match_state.set_partner(partner_id, vid)\n")
        new_lines.append("        await match_state.set_user_state(vid, UnifiedState.CHAT_ACTIVE)\n")
        new_lines.append("        await match_state.set_user_state(partner_id, UnifiedState.CHAT_ACTIVE)\n")
        if "match_state.active_chats[partner_id] = vid" in lines[i+1]:
            skip = 1
        continue

    new_lines.append(line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print("Updated successfully")
