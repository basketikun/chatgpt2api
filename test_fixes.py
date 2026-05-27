import json, re

# Test 1: XML extraction
from services.protocol.openai_v1_chat_complete import _extract_xml_tool_calls_from_text
xml_text = '```xml\n<tool_call name="GetLiveContext">{}</tool_call>\n```'
result = _extract_xml_tool_calls_from_text(xml_text)
print('Test 1 - XML extraction:', 'PASS' if result and result[0].get('function',{}).get('name') == 'GetLiveContext' else 'FAIL')

# Test 2: GetLiveContext handler exists (code check, not runtime config)
from services.ha_client import execute_ha_tool
import inspect
src = inspect.getsource(execute_ha_tool)
print('Test 2 - GetLiveContext handler:', 'PASS' if 'GetLiveContext' in src else 'FAIL')

# Test 3: file upload triggers when payload > 100KB with a single huge message
from services.protocol.conversation import _rtk_compress_messages, _file_upload_store, _FILE_UPLOAD_MARKER
_file_upload_store.clear()
# Need total payload > 100KB so early-return doesn't skip compression
big = 'X' * 110_000
msg1 = {'role': 'system', 'content': 'System prompt here'}
msg2 = {'role': 'user', 'content': big + '\n\nCau hoi cuoi cung'}
messages = [msg1, msg2]
compressed = _rtk_compress_messages(messages, max_bytes=100_000, file_upload_threshold=80_000)
c2 = compressed[1]['content']  # user message should have marker
print('Test 3 - File upload for large message:', 'PASS' if c2.startswith(_FILE_UPLOAD_MARKER) and len(_file_upload_store) > 0 else 'FAIL')
print('  Compressed:', len(c2.encode('utf-8')), 'bytes, Store:', len(_file_upload_store))
_file_upload_store.clear()

# Test 4: XML fence strip
xml_fence = 'Some text\n```xml\n<tool_call name="Test">{}</tool_call>\n```\nMore text'
clean = re.sub(r"```xml\s*<tool_call[^`]*```", '', xml_fence, flags=re.DOTALL).strip()
print('Test 4 - XML fence strip:', 'PASS' if clean == 'Some text\nMore text' else 'FAIL', '- got:', repr(clean))

print()
print('DONE')
