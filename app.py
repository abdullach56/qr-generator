from flask import Flask, request, render_template_string, Response
from flask import jsonify
from PIL import Image
import io, base64
import pyzbar.pyzbar as pyzbar

app = Flask(__name__)

HTML = r'''
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Smart QR — Scanner</title>
<link rel="manifest" href="/manifest.json">
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<script src="https://unpkg.com/html5-qrcode"></script>
<style>
  :root{--bg:#0f172a;--card:#111827;--muted:#94a3b8;--text:#e2e8f0;--accent:#6366f1}
  html,body{height:100%;margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial}
  .wrap{max-width:520px;margin:28px auto;padding:16px}
  .card{background:var(--card);border-radius:12px;padding:18px;box-shadow:0 8px 30px rgba(0,0,0,.35)}
  #reader{width:100%;border-radius:10px;overflow:hidden;background:#000}
  .preview-img{max-width:220px;max-height:220px;border-radius:8px;margin-top:12px}
  .small{font-size:.9rem;color:var(--muted)}
  .btn-primary{background:var(--accent);border:0}
  @media(min-width:900px){ .wrap{margin-top:40px} }
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <div class="d-flex align-items-center">
      <h3 class="mb-0">Smart QR — Scanner</h3>
      <button id="themeBtn" class="btn btn-ghost small ms-auto" style="display:none">Theme</button>
    </div>
    <p class="small mt-2">Scan with camera or upload an image. If the QR contains a link/UPI, an Open button appears.</p>

    <hr style="border-color:rgba(255,255,255,0.04)">

    <div><strong>Camera scan</strong></div>
    <div id="reader" class="my-2"></div>
    <div class="mt-2 d-flex gap-2">
      <button id="openBtn" class="btn btn-primary" style="display:none">Open / Pay</button>
      <a id="directLink" class="btn btn-ghost" style="display:none;color:var(--text);text-decoration:none">Tap to open</a>
      <button id="copyScanned" class="btn btn-ghost" style="display:none">Copy</button>
      <button id="shareScanned" class="btn btn-ghost" style="display:none">Share</button>
    </div>
    <div id="scannedText" class="small mt-2"></div>

    <hr style="border-color:rgba(255,255,255,0.04)">

    <div><strong>Scan from image</strong></div>
    <form id="uploadForm" method="POST" enctype="multipart/form-data" class="mt-2">
      <input type="file" name="qrfile" id="qrfile" accept="image/*" class="form-control" />
      <div class="mt-2 d-flex gap-2">
        <button class="btn btn-primary" type="submit">Scan</button>
        <button id="clearBtn" type="button" class="btn btn-ghost">Clear</button>
      </div>
    </form>

    {% if img_data %}
      <img src="data:image/png;base64,{{ img_data }}" class="preview-img" alt="preview">
    {% endif %}

    {% if result %}
      <div class="alert alert-info mt-3" role="alert">
        <strong>Decoded:</strong><br>{{ result|e }}
        {% if result.startswith('http://') or result.startswith('https://') or result.startswith('upi://') or result.startswith('mailto:') %}
          <div class="mt-2">
            <a href="{{ result }}" target="_blank" class="btn btn-success btn-sm">Open Link / App</a>
          </div>
        {% endif %}
      </div>
    {% elif error %}
      <div class="alert alert-danger mt-3">{{ error }}</div>
    {% endif %}

    <div class="small mt-3 text-muted">Tip: on mobile allow the camera; if the Open button doesn't do anything the target app may be missing or not configured.</div>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
const isUPI = s => s && s.trim().toLowerCase().startsWith('upi://');
const isHttp = s => s && (s.startsWith('http://') || s.startsWith('https://'));
const openBtn = $('openBtn');
const directLink = $('directLink');
const scannedText = $('scannedText');
const copyScanned = $('copyScanned');
const shareScanned = $('shareScanned');

function openViaAnchor(url, target){
  try {
    const a = document.createElement('a');
    a.href = url;
    a.target = target || '_self';
    a.rel = 'noopener noreferrer';
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    return true;
  } catch(e) { return false; }
}

function handleOpen(text){
  if(isUPI(text)){
    // show basic chooser via intent (android) or fallback
    const payload = text.replace(/^upi:\/\//i,'');
    const intentUrl = 'intent://' + payload + '#Intent;scheme=upi;end';
    openViaAnchor(intentUrl,'_self');
    setTimeout(()=> openViaAnchor(text,'_self'), 800);
    setTimeout(()=> alert('If nothing opened, app may be missing or not configured.'), 1500);
  } else if(isHttp(text)){
    openViaAnchor(text,'_blank');
  } else {
    alert('No handler available. Use copy to paste into the target app.');
  }
}

function onScanSuccess(decodedText){
  scannedText.textContent = 'Scanned: ' + decodedText;
  copyScanned.style.display = 'inline-block';
  shareScanned.style.display = 'inline-block';
  copyScanned.onclick = async ()=> { try{ await navigator.clipboard.writeText(decodedText); alert('Copied'); }catch(e){ alert('Copy failed'); } };
  shareScanned.onclick = ()=> { if(navigator.share){ navigator.share({text: decodedText}).catch(()=> window.open('https://wa.me/?text='+encodeURIComponent(decodedText),'_blank')); } else { window.open('https://wa.me/?text='+encodeURIComponent(decodedText),'_blank'); } };

  if(isUPI(decodedText) || isHttp(decodedText)){
    openBtn.style.display = 'inline-block';
    directLink.style.display = 'inline-block';
    directLink.href = decodedText;
    openBtn.onclick = ()=> handleOpen(decodedText);
  } else {
    openBtn.style.display = 'none';
    directLink.style.display = 'none';
  }
}

const scanner = new Html5QrcodeScanner('reader', { fps: 10, qrbox: 250, rememberLastUsedCamera: true });
scanner.render(onScanSuccess, (err)=>{ /* ignore */ });

// upload form uses normal POST to server; keep UX friendly by disabling submit if no file
const uploadForm = document.getElementById('uploadForm');
const fileInput = document.getElementById('qrfile');
const clearBtn = document.getElementById('clearBtn');
clearBtn.onclick = ()=> { fileInput.value=''; window.location = '/'; };

uploadForm.addEventListener('submit', (e)=>{
  const f = fileInput.files[0];
  if(!f){ e.preventDefault(); alert('Choose an image file first.'); }
});
</script>
</body>
</html>
'''

MANIFEST = {
  "name": "Smart QR Scanner",
  "short_name": "SmartQR",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#0f172a",
  "theme_color": "#6366f1",
  "icons": [
    {"src":"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAQAAAAAYLlVAAA...","sizes":"64x64","type":"image/png"}
  ]
}

SERVICE_WORKER = "self.addEventListener('install',e=>self.skipWaiting()); self.addEventListener('fetch',e=>{});"

@app.route("/", methods=["GET","POST"])
def index():
    result = error = img_data = None
    if request.method == "POST":
        file = request.files.get("qrfile")
        if not file:
            error = "No file uploaded."
        else:
            try:
                img = Image.open(file.stream).convert("RGB")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                img_data = base64.b64encode(buf.getvalue()).decode("ascii")
                decoded = pyzbar.decode(img)
                if decoded:
                    result = "\n".join([d.data.decode("utf-8") for d in decoded])
                else:
                    error = "No QR found in the provided image."
            except Exception as e:
                error = f"Error reading image: {e}"
    return render_template_string(HTML, result=result, error=error, img_data=img_data)

@app.get("/manifest.json")
def manifest():
    return jsonify(MANIFEST) 

@app.get("/service-worker.js")
def sw():
    return Response(SERVICE_WORKER, mimetype="application/javascript") 

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=False) 
