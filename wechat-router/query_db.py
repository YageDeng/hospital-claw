"""Query captured messages from the database."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from src.storage import StorageManager

s = StorageManager("data/wechat_monitor.db")
msgs = s.get_messages(limit=20)
print(f"Total messages in DB: {len(msgs)}\n")
for m in msgs:
    text = (m["text_content"] or "(no text)")[:120]
    print(f"[{m['contact_name']}] type={m['content_type']} sender={m['sender']}")
    print(f"  text: {text}")
    print(f"  timestamp_ocr: {m['timestamp_ocr']}  captured_at: {m['captured_at']}")
    print()
s.close()
