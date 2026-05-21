"""Studio HTML page — served directly by FastAPI at GET /studio.

Tabs: MCP Servers | Cai dat | R2 Storage | External MCP
"""

STUDIO_HTML = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VN MCP Hub — Studio</title>
<style>
  :root { --bg: #0f172a; --card: #1e293b; --border: #334155; --text: #e2e8f0;
          --muted: #94a3b8; --accent: #3b82f6; --danger: #ef4444; --ok: #22c55e; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: var(--bg); color: var(--text);
         padding: 2rem; max-width: 1000px; margin: 0 auto; }
  h1 { font-size: 1.5rem; margin-bottom: .5rem; }
  .tabs { display: flex; gap: .5rem; margin-bottom: 1.5rem; border-bottom: 1px solid var(--border); padding-bottom: .5rem; }
  .tab { padding: .5rem 1.2rem; border: 1px solid var(--border); border-radius: 6px 6px 0 0;
         background: transparent; color: var(--muted); cursor: pointer; font-size: .9rem; border-bottom: none; }
  .tab.active { background: var(--card); color: var(--text); border-color: var(--accent); }
  .tab-content { display: none; }
  .tab-content.active { display: block; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px;
          padding: 1.5rem; margin-bottom: 1.5rem; }
  .card h2 { font-size: 1.1rem; margin-bottom: 1rem; }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: .5rem; border-bottom: 1px solid var(--border); }
  th { color: var(--muted); font-weight: 500; font-size: .85rem; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: .75rem; }
  .badge-ok { background: var(--ok); color: #000; }
  .badge-warn { background: #f59e0b; color: #000; }
  label { display: block; margin-bottom: .3rem; font-weight: 500; }
  input, textarea, select { width: 100%; padding: .6rem; background: var(--bg);
                    border: 1px solid var(--border); border-radius: 6px;
                    color: var(--text); margin-bottom: 1rem; font-family: monospace; }
  textarea { min-height: 120px; resize: vertical; }
  button { padding: .6rem 1.2rem; border: none; border-radius: 6px; cursor: pointer; font-weight: 500; }
  .btn-go { background: var(--accent); color: #fff; }
  .btn-del { background: var(--danger); color: #fff; }
  .btn-sm { padding: .2rem .5rem; font-size: .75rem; }
  .toast { position: fixed; top: 1rem; right: 1rem; padding: .8rem 1.2rem;
           border-radius: 6px; color: #fff; display: none; z-index: 100; }
  .toast-ok { background: var(--ok); color: #000; }
  .toast-err { background: var(--danger); }
  .src-row { display: flex; align-items: center; justify-content: space-between; padding: .3rem 0; font-size: .85rem; }
  .src-row label { margin: 0; cursor: pointer; }
  .src-toggle { width: 16px; height: 16px; cursor: pointer; accent-color: var(--ok); }
  .expand-btn { background: none; border: 1px solid var(--border); color: var(--muted);
                padding: .2rem .5rem; border-radius: 4px; cursor: pointer; font-size: .75rem; }
  .expand-btn:hover { color: var(--text); border-color: var(--text); }
  .src-panel { display: none; padding: .5rem 0 0 1rem; border-top: 1px solid var(--border); margin-top: .5rem; }
  .src-panel.open { display: block; }
  .key-input { width: auto; display: inline-block; padding: .3rem; font-size: .75rem; margin: .2rem 0 .5rem 0; }
  .key-saved { color: var(--ok); font-size: .7rem; margin-left: .5rem; }
  .help-text { color: var(--muted); font-size: .72rem; display: block; margin-bottom: .2rem; }
  .status-ok { color: var(--ok); font-size: .85rem; margin-left: 1rem; }
</style>
</head>
<body>
<h1>VN MCP Hub — Studio</h1>

<div class="tabs">
  <button class="tab active" onclick="switchTab('mcp')">MCP Servers</button>
  <button class="tab" onclick="switchTab('settings')">Cai dat</button>
  <button class="tab" onclick="switchTab('r2')">R2 Storage</button>
  <button class="tab" onclick="switchTab('external')">External MCP</button>
</div>

<div id="toast" class="toast"></div>

<!-- TAB: MCP Servers -->
<div id="tab-mcp" class="tab-content active">
  <div class="card">
    <h2>Tao KB moi</h2>
    <form id="createForm">
      <label for="name">Ten collection (slug)</label>
      <input id="name" placeholder="vi_du_1" required pattern="[a-z0-9_]+" maxlength="30">
      <label for="label">Nhan hien thi</label>
      <input id="label" placeholder="Kho tri thuc ve...">
      <label for="content">Noi dung markdown</label>
      <textarea id="content" placeholder="Dan noi dung markdown vao day..." required></textarea>
      <button type="submit" class="btn-go">Tao MCP</button>
    </form>
  </div>
  <div class="card">
    <h2>Danh sach MCP</h2>
    <table>
      <thead><tr><th>Ten</th><th>Nhan</th><th>Chunks</th><th>Cap nhat</th><th>Sources</th><th></th></tr></thead>
      <tbody id="mcpTable"><tr><td colspan="6">Dang tai...</td></tr></tbody>
    </table>
  </div>
</div>

<!-- TAB: Settings -->
<div id="tab-settings" class="tab-content">
  <div class="card">
    <h2>RAG Lifecycle</h2>
    <form id="settingsForm">
      <label for="syncInterval">Dong bo R2 (phut)</label>
      <input id="syncInterval" type="number" min="10" value="360">
      <p style="color:var(--muted);font-size:.75rem;margin-bottom:1rem">Kiem tra R2.</p>
      <label for="storageMode">Che do luu tru</label>
      <select id="storageMode" style="width:100%;padding:.6rem;background:var(--bg);border:1px solid var(--border);border-radius:6px;color:var(--text);margin-bottom:1rem">
        <option value="local">Local only (ChromaDB)</option>
        <option value="cloud">Cloud only (R2)</option>
        <option value="both">Ca hai (Local + Cloud)</option>
      </select>
      <label for="autoUpdateInterval">Kiem tra auto-update (gio)</label>
      <input id="autoUpdateInterval" type="number" min="1" max="720" value="1">
      
      <h3 style="margin-top:1.5rem">AI Settings</h3>
      <label for="apiBaseUrl">API Base URL</label>
      <input id="apiBaseUrl" placeholder="http://chatgpt2api:3030/v1">
      <label for="apiKey">API Key</label>
      <input id="apiKey" type="password" placeholder="AnhNhi@0610">
      
      <label for="aiModel">AI Model tong hop RAG</label>
      <div style="display:flex; gap:8px;">
        <select id="aiModel" style="flex:1">
          <option value="cx/auto">cx/auto</option>
          <option value="chatgpt/auto">chatgpt/auto</option>
        </select>
        <button type="button" class="btn-sm" onclick="fetchModels()" style="padding:0 8px" title="Tai danh sach model tu chatgpt2api">🔄</button>
      </div>

      <button type="submit" class="btn-go" style="margin-top:1rem">Luu cai dat</button>
      <span id="settingsStatus" class="status-ok"></span>
    </form>
  </div>
  <div class="card"><h2>Cai dat API Keys</h2><p style="color:var(--muted);font-size:.85rem;margin-bottom:1rem">API key duoc luu trong data/studio/api_keys.json</p><div id="apiKeyList">Dang tai...</div></div>
</div>

<!-- TAB: R2 Storage -->
<div id="tab-r2" class="tab-content">
  <div class="card">
    <h2>Cau hinh Cloudflare R2</h2>
    <p style="color:var(--muted);font-size:.85rem;margin-bottom:1rem">Luu tru RAG len cloud. <a href="https://dash.cloudflare.com/" target="_blank" style="color:var(--accent)">Lay API token</a></p>
    <form id="r2Form">
      <label for="r2endpoint">Endpoint (S3 API)</label>
      <input id="r2endpoint" placeholder="https://{id}.r2.cloudflarestorage.com">
      <label for="r2bucket">Ten Bucket</label>
      <input id="r2bucket" placeholder="vn-mcp-hub-rag">
      <label for="r2key">Access Key ID</label>
      <input id="r2key" placeholder="...">
      <label for="r2secret">Secret Access Key</label>
      <input id="r2secret" type="password" placeholder="...">
      <button type="submit" class="btn-go">Luu cau hinh R2</button>
      <span id="r2Status" class="status-ok"></span>
    </form>
  </div>
  <div class="card"><h2>RAG Collections tren R2</h2><table id="r2Table"><tr><td>Dang tai...</td></tr></table></div>
</div>

<!-- TAB: External MCP -->
<div id="tab-external" class="tab-content">
  <div class="card">
    <h2>Kiem tra MCP Server</h2>
    <p style="color:var(--muted);font-size:.85rem;margin-bottom:1rem">Nhap URL MCP de kiem tra truoc khi them.</p>
    <form id="validateForm">
      <label for="extUrl">URL MCP</label>
      <input id="extUrl" placeholder="https://example.com/mcp">
      <label for="extKey">API Key (neu can)</label>
      <input id="extKey" type="password" placeholder="De trong neu khong can">
      <button type="submit" class="btn-go">Kiem tra</button>
    </form>
    <div id="validateResult" style="margin-top:1rem"></div>
  </div>
  <div class="card" id="addCard" style="display:none">
    <h2>Them MCP</h2>
    <form id="addMcpForm">
      <label for="extName">Ten MCP</label>
      <input id="extName">
      <label for="extDesc">Mo ta (de AI biet MCP nay lam gi)</label>
      <input id="extDesc">
      <button type="submit" class="btn-go">Them MCP</button>
    </form>
  </div>
  <div class="card"><h2>External MCPs da them</h2><table id="extTable"><tr><td>Dang tai...</td></tr></table></div>
</div>

<script>
const API = '/api/studio';
function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.querySelector('.tab[onclick*="'+name+'"]').classList.add('active');
  document.getElementById('tab-'+name).classList.add('active');
  if (name === 'r2') loadR2Data();
  if (name === 'settings') loadApiKeyList();
  if (name === 'external') loadExternalMcps();
}
async function toast(msg, ok) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.className = 'toast ' + (ok ? 'toast-ok' : 'toast-err');
  t.style.display = 'block'; setTimeout(() => t.style.display = 'none', 3000);
}
// ── MCP Servers ──
async function refresh() {
  const [mcpR, srcR] = await Promise.all([fetch(API+'/mcps'),fetch(API+'/sources')]);
  const data = await mcpR.json(); const srcData = await srcR.json(); const allSources = srcData.sources || {};
  const kbNames = (data.mcps||[]).filter(m => m.name.startsWith('kb_')).map(m => m.name);
  const metaMap = {};
  await Promise.all(kbNames.map(async n => { try { const r = await fetch(API+'/collection/'+encodeURIComponent(n)+'/meta'); metaMap[n] = await r.json(); } catch(e) {} }));
  const tbody = document.getElementById('mcpTable');
  if (!data.mcps || !data.mcps.length) { tbody.innerHTML = '<tr><td colspan="6">Chua co MCP.</td></tr>'; return; }
  tbody.innerHTML = data.mcps.map(m => {
    const builtin = m.builtin;
    const refreshBtn = m.name.startsWith('kb_') ? `<button class="btn-go btn-sm" onclick="forceRefresh('${m.name}')" style="margin-right:4px">Update</button>` : '';
    const delBtn = builtin ? '' : `<button class="btn-del btn-sm" onclick="del('${m.name}')">Xoa</button>`;
    const actions = refreshBtn + delBtn;
    const badge = builtin ? '<span class="badge badge-ok">built-in</span>' : '<span class="badge badge-warn">dynamic</span>';
    const srcCfg = allSources[m.name] || {}; const srcCount = Object.keys(srcCfg).length;
    const srcBtn = srcCount > 0 ? `<button class="expand-btn" onclick="toggleSources('${m.name}')">${srcCount} src</button>` : '';
    const meta = metaMap[m.name] || {}; const age = meta.age || '-';
    const autoIcon = (meta.meta && meta.meta.auto_update) ? ' R' : '';
    const ageBtn = m.name.startsWith('kb_') ? `<button class="expand-btn" onclick="showSettings('${m.name}',${meta.meta?meta.meta.update_interval_hours||168:168},${meta.meta?meta.meta.auto_update||false:false})">${age}${autoIcon}</button>` : age;
    let srcPanel = '';
    if (srcCount > 0) {
      srcPanel = '<div class="src-panel" id="src-'+m.name+'">' + Object.entries(srcCfg).map(([k,v]) => {
        const enabled = typeof v === 'object' ? v.enabled : v;
        const help = typeof v === 'object' ? (v.help||'') : '';
        const needsKey = typeof v === 'object' ? v.needsKey : false;
        const hasKey = typeof v === 'object' ? v.hasKey : false;
        const helpHtml = help ? `<span class="help-text">${help}</span>` : '';
        const keyHtml = needsKey ? `<input class="key-input" type="password" placeholder="${hasKey?'Da co key':'Nhap API key...'}" onchange="saveKey('${k}',this.value)" style="width:200px">${hasKey?'<span class=\"key-saved\">OK</span>':''}` : '';
        return `<div class="src-row"><div><label>${k}</label>${helpHtml}${keyHtml}</div><input type="checkbox" class="src-toggle" ${enabled?'checked':''} onchange="toggleSource('${m.name}','${k}',this.checked)"></div>`;
      }).join('') + '</div>';
    }
    return `<tr><td>${badge} ${m.name}</td><td>${m.label||m.name}</td><td>${m.chunks||'-'}</td><td>${ageBtn}</td><td>${srcBtn}</td><td>${actions}</td></tr><tr id="src-row-${m.name}" style="display:none"><td colspan="6">${srcPanel}</td></tr>`;
  }).join('');
}
async function forceRefresh(name) {
  if (!confirm('Chay tong hop AI thu cong cho ' + name + '? (Mat vai phut)')) return;
  toast('Dang kich hoat tong hop AI...', true);
  try {
    const r = await fetch('/api/rag/refresh/' + encodeURIComponent(name), {method: 'POST'});
    const d = await r.json();
    toast(d.message || 'Da gui yeu cau', d.ok);
  } catch(e) { toast('Loi', false); }
}
function toggleSources(name) { const row = document.getElementById('src-row-'+name), panel = document.getElementById('src-'+name); if (row && panel) { const open = row.style.display !== 'none'; row.style.display = open ? 'none' : 'table-row'; panel.className = 'src-panel' + (open ? '' : ' open'); } }
async function toggleSource(mcp, source, enabled) { await fetch(API+'/sources/'+encodeURIComponent(mcp),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({[source]:enabled})}); toast(source+' '+(enabled?'ON':'OFF'),true); }
async function saveKey(source, value) { if (!value) return; const r = await fetch(API+'/key/'+encodeURIComponent(source),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({api_key:value})}); if ((await r.json()).ok) toast('Da luu API key cho '+source, true); }
async function del(name) { if (!confirm('Xoa KB '+name+'?')) return; const r = await fetch(API+'/kb/'+encodeURIComponent(name),{method:'DELETE'}); const d = await r.json(); if (d.ok) { toast('Da xoa '+name,true); refresh(); } else toast(d.error||'Loi',false); }
function showSettings(name, interval, autoUpdate) { const h = prompt('Chu ky cap nhat (gio):', interval); if (h === null) return; const auto = confirm('Bat tu dong cap nhat?'); fetch(API+'/collection/'+encodeURIComponent(name)+'/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({update_interval_hours:parseInt(h),auto_update:auto})}).then(r=>r.json()).then(d=>{if(d.ok)toast('Da luu',true);refresh();}); }
document.getElementById('createForm').onsubmit = async (e) => { e.preventDefault(); const body = JSON.stringify({name:document.getElementById('name').value.trim(),label:document.getElementById('label').value.trim(),content:document.getElementById('content').value}); const r = await fetch(API+'/kb',{method:'POST',headers:{'Content-Type':'application/json'},body}); const d = await r.json(); if (d.ok) { toast('Da tao '+d.name+' ('+d.chunks+' chunks)',true); document.getElementById('createForm').reset(); refresh(); } else toast((d.errors||['Loi']).join('. '),false); };
refresh();
// ── Settings ──
(async function(){ try { const r = await fetch(API+'/settings'); const d = await r.json(); document.getElementById('syncInterval').value = d.sync_interval_minutes || 360; document.getElementById('storageMode').value = d.storage_mode || 'local'; document.getElementById('autoUpdateInterval').value = d.auto_update_interval_hours || 1; document.getElementById('apiBaseUrl').value = d.api_base_url || 'http://chatgpt2api:3030/v1'; document.getElementById('aiModel').value = d.ai_model || 'cx/auto'; document.getElementById('apiKey').value = d.api_key || 'AnhNhi@0610'; fetchModels(); } catch(e) {} })();
document.getElementById('settingsForm').onsubmit = async (e) => { e.preventDefault(); const body = JSON.stringify({sync_interval_minutes:parseInt(document.getElementById('syncInterval').value),storage_mode:document.getElementById('storageMode').value,auto_update_interval_hours:parseInt(document.getElementById('autoUpdateInterval').value),api_base_url:document.getElementById('apiBaseUrl').value.trim()||'http://chatgpt2api:3030/v1',ai_model:document.getElementById('aiModel').value.trim()||'cx/auto',api_key:document.getElementById('apiKey').value.trim()}); const r = await fetch(API+'/settings',{method:'POST',headers:{'Content-Type':'application/json'},body}); if ((await r.json()).ok) { document.getElementById('settingsStatus').textContent = 'Da luu!'; toast('Cai dat da luu',true); fetchModels(); } };
async function fetchModels() {
  try {
    const select = document.getElementById('aiModel');
    const r = await fetch('/api/rag/models');
    const d = await r.json();
    if (d.ok && d.models) {
      const currentVal = select.value;
      select.innerHTML = d.models.map(m => `<option value="${m}">${m}</option>`).join('');
      if (d.models.includes(currentVal)) {
        select.value = currentVal;
      } else if (currentVal) {
        select.innerHTML += `<option value="${currentVal}">${currentVal}</option>`;
        select.value = currentVal;
      }
      toast('Da tai danh sach models', true);
    } else {
      toast('Loi tai models: ' + (d.error || ''), false);
    }
  } catch(e) { toast('Khong ket noi duoc API', false); }
}
async function loadApiKeyList() { try { const r = await fetch(API+'/sources'); const d = await r.json(); const list = document.getElementById('apiKeyList'); let html = ''; for (const [mcp, srcs] of Object.entries(d.sources||{})) { for (const [name, info] of Object.entries(srcs)) { if (info.needs_key) { html += `<div class="src-row"><div><label>${name} (${mcp})</label><span class="help-text">${info.help||''}</span></div><input class="key-input" type="password" placeholder="${info.has_key?'*** Da co ***':'Nhap key...'}" onchange="saveKey('${name}',this.value)" style="width:250px"><span class="key-saved">${info.has_key?'OK':''}</span></div>`; } } } list.innerHTML = html || '<p style="color:var(--muted)">Khong co source nao can API key.</p>'; } catch(e) {} }
// ── R2 ──
(async function(){ try { const r = await fetch(API+'/r2'); const d = await r.json(); if (d.configured) { document.getElementById('r2endpoint').value = d.config.endpoint||''; document.getElementById('r2bucket').value = d.config.bucket||''; document.getElementById('r2key').value = d.config.access_key_id||''; document.getElementById('r2secret').value = d.config.secret_access_key||''; document.getElementById('r2Status').textContent = 'Da cau hinh'; } } catch(e) {} })();
document.getElementById('r2Form').onsubmit = async (e) => { e.preventDefault(); const body = JSON.stringify({endpoint:document.getElementById('r2endpoint').value.trim(),bucket:document.getElementById('r2bucket').value.trim(),access_key_id:document.getElementById('r2key').value.trim(),secret_access_key:document.getElementById('r2secret').value.trim()}); const r = await fetch(API+'/r2',{method:'POST',headers:{'Content-Type':'application/json'},body}); if ((await r.json()).ok){document.getElementById('r2Status').textContent='Da luu!';toast('Cau hinh R2 da luu',true)} };
async function loadR2Data() { try { const listR = await fetch('/api/rag/list'); const list = await listR.json(); let html = '<tr><th>Collection</th><th>Chunks</th><th>Cap nhat</th><th>Hoat dong</th></tr>'; (list.collections||[]).forEach(c => { html += `<tr><td>${c.name}</td><td>${c.chunks}</td><td>${c.age}</td><td><button class="btn-go btn-sm" onclick="fetch('/api/rag/upload/'+encodeURIComponent('${c.name}'),{method:'POST'}).then(r=>r.json()).then(d=>toast(d.ok?'Upload OK':'Upload fail',d.ok))">Upload R2</button></td></tr>`; }); document.getElementById('r2Table').innerHTML = html; } catch(e) {} }
// ── External MCP ──
let validatedUrl = '';
document.getElementById('validateForm').onsubmit = async (e) => { e.preventDefault(); const url = document.getElementById('extUrl').value.trim(); const key = document.getElementById('extKey').value.trim(); if (!url) return; document.getElementById('validateResult').innerHTML = '<p style="color:var(--muted)">Dang kiem tra...</p>'; const r = await fetch(API+'/validate-mcp',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url,api_key:key})}); const d = await r.json(); if (d.ok) { validatedUrl = url; document.getElementById('extName').value = d.name||''; document.getElementById('addCard').style.display = 'block'; let html = '<p style="color:var(--ok);margin-bottom:.5rem">OK - '+d.name+' v'+d.version+' - '+d.tools_count+' tools</p><ul>'; (d.tools||[]).forEach(t => { html += '<li style="font-size:.85rem"><strong>'+t.name+'</strong>: '+t.description+'</li>'; }); html += '</ul>'; document.getElementById('validateResult').innerHTML = html; } else { validatedUrl = ''; document.getElementById('addCard').style.display = 'none'; document.getElementById('validateResult').innerHTML = '<p style="color:var(--danger)">Loi: '+(d.errors||[]).join('. ')+'</p>'; } };
document.getElementById('addMcpForm').onsubmit = async (e) => { e.preventDefault(); const body = JSON.stringify({name:document.getElementById('extName').value.trim(),url:validatedUrl,description:document.getElementById('extDesc').value.trim(),api_key:document.getElementById('extKey').value.trim()}); const r = await fetch(API+'/external-mcp',{method:'POST',headers:{'Content-Type':'application/json'},body}); const d = await r.json(); if (d.ok) { toast('Da them '+d.name,true); loadExternalMcps(); document.getElementById('addCard').style.display='none'; } else toast((d.errors||['Loi']).join('. '),false); };
async function loadExternalMcps() { try { const r = await fetch(API+'/external-mcps'); const d = await r.json(); let html = '<tr><th>Ten</th><th>URL</th><th>Mo ta</th><th></th></tr>'; (d.mcps||[]).forEach(m => { html += '<tr><td>'+m.name+'</td><td><code style="font-size:.75rem">'+m.url+'</code></td><td>'+(m.description||'')+'</td><td><button class="btn-del btn-sm" onclick="delExt(\"'+m.name+'\")">Xoa</button></td></tr>'; }); document.getElementById('extTable').innerHTML = html; } catch(e) {} }
async function delExt(name) { if (!confirm('Xoa MCP '+name+'?')) return; await fetch(API+'/external-mcp/'+encodeURIComponent(name),{method:'DELETE'}); toast('Da xoa '+name,true); loadExternalMcps(); }
loadExternalMcps();
</script>
</body>
</html>"""
