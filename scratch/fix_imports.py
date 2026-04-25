import re

with open('core/engine/actions.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Lines to remove entirely (careful with indentation)
patterns = [
    r'^[ \t]*from services\.distributed_state import distributed_state\n',
    r'^[ \t]*from database\.repositories\.user_repository import UserRepository\n',
    r'^[ \t]*from utils\.platform_adapter import PlatformAdapter\n',
    r'^[ \t]*from core\.telemetry import TelemetryEvent\n',
]

for p in patterns:
    content = re.sub(p, '', content, flags=re.MULTILINE)

with open('core/engine/actions.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Imports fixed.")
