from flask import Flask, request, jsonify, render_template_string
import io
import base64
import re
from PIL import Image
import qrcode
import qrcode.constants

app = Flask(__name__)

# -----------------------------
# Utility: Smart eligibility scan (AI-lite)
# -----------------------------
BLOCKED_PROTOCOLS = ("javascript:", "data:", "file:")
BLOCKED_DOMAINS = {"localhost", "127.0.0.1"}
BAD_WORDS = {"hack", "malware", "phishing", "exploit"}

URL_RE = re.compile(r"^(https?://)([^/]+)(/.*)?$", re.IGNORECASE)


def smart_scan(text: str):
    """Return (eligible: bool, reason: str). Conservative rules to keep it offline.
    - Allows http(s) URLs that are not obviously risky
    - Allows plain text up to 800 chars
    - Blocks empty, unsupported protocols, extreme lengths, or flagged words
    """
    if not text or not text.strip():
        return False, "Input is empty."

    text = text.strip()

    # Hard length guard
    if len(text) > 5000:
        return False, "Input is too long. Keep it under 5000 characters."

    # Block control chars
    if any(ord(c) < 9 for c in text):
        return False, "Input contains invalid control characters."

    # URL path
    m = URL_RE.match(text)
    if m:
        scheme, host, _ = m.groups()
        # Protocol check
        if scheme.lower() not in ("http://", "https://"):
            return False, "Only http/https links are allowed."
        # Localhost guard
        host_l = host.lower()
        if host_l in BLOCKED_DOMAINS:
            return False, "Local/loopback links are not allowed."
        # length guard
        if len(text) > 2000:
            return False, "URL is too long. Keep it under 2000 characters."
        # Bad words guard (very light)
        if any(b in text.lower() for b in BAD_WORDS):
            return False, "URL failed the safety scan."
        return True, "OK"

    # Plain text path
    if len(text) > 800:
        return False, "Text is too long. Keep it under 800 characters."
    if any(b in text.lower() for b in BAD_WORDS):
        return False, "Text failed the safety scan."

    return True, "OK"


# -----------------------------
# QR generation
# -----------------------------
ECC_MAP = {
    "L": qrcode.constants.ERROR_CORRECT_L,
    "M": qrcode.constants.ERROR_CORRECT_M,
    "Q": qrcode.constants.ERROR_CORRECT_Q,
    "H": qrcode.constants.ERROR_CORRECT_H,
}


def make_qr_image(data: str, fg: str, bg: str, box_size: int, border: int, ecc: str, logo_image: Image.Image | None):
    qr = qrcode.QRCode(
        version=None,  # let it auto-size
        error_correction=ECC_MAP.get(ecc, qrcode.constants.ERROR_CORRECT_H),
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color=fg, back_color=bg).convert("RGBA")

    # Optional logo: place centered ~20% of QR width
    if logo_image is not None:
        # ensure RGBA
        logo = logo_image.convert("RGBA")
        qr_w, qr_h = img.size
        max_logo = int(min(qr_w, qr_h) * 0.22)
        logo.thumbnail((max_logo, max_logo), Image.LANCZOS)
        lx = (qr_w - logo.width) // 2
        ly = (qr_h - logo.height) // 2
        img.alpha_composite(logo, dest=(lx, ly))

    return img


# -----------------------------
# Routes
# -----------------------------

INDEX_HTML = """
<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Smart QR – Generator</title>
    <link href=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css\" rel=\"stylesheet\" />
    <style>
      body { background: #0f172a; color: #e2e8f0; }
      .app-card { max-width: 720px; margin: 24px auto; background: #111827; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,.35); }
      .gradient-bar { height: 4px; background: linear-gradient(90deg, #22d3ee, #a78bfa, #f472b6); border-top-left-radius: 16px; border-top-right-radius: 16px; }
      .btn-primary { background: #6366f1; border: none; }
      .btn-primary:hover { filter: brightness(1.05); }
      .btn-danger { background: #ef4444; border: none; }
      .preview-wrap { background: #0b1220; border: 1px solid #1f2937; border-radius: 12px; padding: 16px; text-align: center; }
      .hint { color: #94a3b8; font-size: .9rem; }
      .form-label { color: #cbd5e1; }
      .brand { font-weight: 800; letter-spacing: .5px; }
      a.link-light { color: #c7d2fe; }
      .footer { opacity: .75; font-size: .9rem; }
      .visually-hidden { position: absolute; left: -9999px; }
    </style>
  </head>
  <body>
    <div class=\"app-card p-3 p-md-4\">
      <div class=\"gradient-bar mb-3\"></div>
      <h1 class=\"brand h3 mb-3\">Smart QR Generator <span class=\"badge bg-info text-dark\">AI‑scan</span></h1>
      <p class=\"hint mb-4\">Paste text or a link. Our AI‑lite scanner checks eligibility before generating. Works great on mobile.</p>

      <form id=\"qform\" class=\"row g-3\" enctype=\"multipart/form-data\">
        <div class=\"col-12\">
          <label class=\"form-label\">Text or URL</label>
          <textarea class=\"form-control\" name=\"data\" rows=\"3\" placeholder=\"https://your-link or any text\" required></textarea>
        </div>

        <div class=\"col-6\">
          <label class=\"form-label\">Foreground</label>
          <input type=\"color\" class=\"form-control form-control-color\" name=\"fg\" value=\"#000000\"/>
        </div>
        <div class=\"col-6\">
          <label class=\"form-label\">Background</label>
          <input type=\"color\" class=\"form-control form-control-color\" name=\"bg\" value=\"#ffffff\"/>
        </div>

        <div class=\"col-6\">
          <label class=\"form-label\">QR Size</label>
          <select class=\"form-select\" name=\"box_size\">
            <option value=\"8\">Small</option>
            <option value=\"10\" selected>Medium</option>
            <option value=\"12\">Large</option>
            <option value=\"16\">XL</option>
          </select>
        </div>
        <div class=\"col-6\">
          <label class=\"form-label\">Error correction</label>
          <select class=\"form-select\" name=\"ecc\">
            <option value=\"L\">L (7%)</option>
            <option value=\"M\" selected>M (15%)</option>
            <option value=\"Q\">Q (25%)</option>
            <option value=\"H\">H (30%)</option>
          </select>
        </div>

        <div class=\"col-12\">
          <label class=\"form-label\">Logo (optional)</label>
          <input class=\"form-control\" type=\"file\" name=\"logo\" accept=\"image/*\" />
          <div class=\"hint mt-1\">PNG with transparency works best.</div>
        </div>

        <div class=\"col-12 d-flex gap-2\">
          <button class=\"btn btn-primary\" type=\"submit\">Generate</button>
          <button class=\"btn btn-secondary\" type=\"button\" id=\"downloadBtn\" disabled>Download PNG</button>
          <button class=\"btn btn-danger ms-auto\" type=\"button\" id=\"clearBtn\">Clear</button>
        </div>
      </form>

      <div class=\"mt-4\">
        <div class=\"preview-wrap\">
          <img id=\"qrImg\" alt=\"QR preview\" class=\"img-fluid\" />
        </div>
        <div id=\"status\" class=\"hint mt-2\">Awaiting input…</div>
      </div>

      <div class=\"footer mt-4\">Built with Flask + Pillow + qrcode. Offline AI‑lite scanner (no cloud).</div>
    </div>

<hr>
<h2 class="mt-4">📷 Scan QR Code</h2>
<div id="reader" style="width:100%; max-width:400px;"></div>
<p id="scan-result" class="mt-2 text-success fw-bold"></p>

<!-- QR Scanner Script -->
<script src="https://unpkg.com/html5-qrcode"></script>
<script>
  function onScanSuccess(decodedText, decodedResult) {
    document.getElementById("scan-result").innerText = "✅ Scanned: " + decodedText;
  }

  function onScanFailure(error) {
    // Failures are common while scanning, ignore them.
  }

  let html5QrcodeScanner = new Html5QrcodeScanner(
    "reader", { fps: 10, qrbox: 250 });
  html5QrcodeScanner.render(onScanSuccess, onScanFailure);
</script>

    <script>
      const form = document.getElementById('qform');
      const img = document.getElementById('qrImg');
      const statusEl = document.getElementById('status');
      const dlBtn = document.getElementById('downloadBtn');
      const clearBtn = document.getElementById('clearBtn');

      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        statusEl.textContent = 'Scanning…';
        dlBtn.disabled = true;

        const fd = new FormData(form);
        const res = await fetch('/api/generate', { method: 'POST', body: fd });
        const data = await res.json();

        if (!data.ok) {
          img.removeAttribute('src');
          statusEl.textContent = '❌ ' + data.message;
          return;
        }

        img.src = 'data:image/png;base64,' + data.image_b64;
        statusEl.textContent = '✅ QR generated';
        dlBtn.disabled = false;
        dlBtn.onclick = () => {
          const a = document.createElement('a');
          a.href = img.src;
          a.download = 'smart_qr.png';
          a.click();
        };
      });

      clearBtn.addEventListener('click', () => {
        form.reset();
        img.removeAttribute('src');
        statusEl.textContent = 'Cleared. Enter text and Generate';
        dlBtn.disabled = true;
      });
    </script>
  </body>
</html>
"""


@app.get("/")
def index():
    return render_template_string(INDEX_HTML)


@app.post("/api/generate")
def api_generate():
    data = request.form.get("data", "").strip()
    fg = request.form.get("fg", "#000000")
    bg = request.form.get("bg", "#ffffff")
    box_size = int(request.form.get("box_size", 10))
    ecc = request.form.get("ecc", "M")

    # Safety/eligibility scan
    ok, reason = smart_scan(data)
    if not ok:
        return jsonify({"ok": False, "message": reason}), 200

    # Logo file (optional)
    logo_file = request.files.get("logo")
    logo_img = None
    if logo_file and logo_file.filename:
        try:
            logo_img = Image.open(logo_file.stream)
        except Exception:
            return jsonify({"ok": False, "message": "Logo image could not be read."}), 200

    try:
        img = make_qr_image(
            data=data,
            fg=fg,
            bg=bg,
            box_size=box_size,
            border=4,
            ecc=ecc,
            logo_image=logo_img,
        )
    except Exception as e:
        return jsonify({"ok": False, "message": f"Failed to generate QR: {e}"}), 200

    # Encode to base64
    buf = io.BytesIO()
    img = img.convert("RGBA")
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    return jsonify({"ok": True, "image_b64": b64}), 200


if __name__ == "__main__":
    # Run in debug for dev; change host to 0.0.0.0 for LAN/mobile testing
    app.run(debug=True)
