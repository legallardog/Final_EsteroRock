import os
import base64
from flask import Flask, render_template, request, send_file
from io import BytesIO
from reportlab.lib.pagesizes import landscape, A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
import qrcode
from PIL import Image
import jwt
import datetime
import uuid
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

app = Flask(__name__)
GENERATED_FILES_DIR = "generated_certificados"
os.makedirs(GENERATED_FILES_DIR, exist_ok=True)

# --- Generar claves RSA si no existen ---
def generate_keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with open("private.pem", "wb") as f:
        f.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            )
        )
    public_key = private_key.public_key()
    with open("public.pem", "wb") as f:
        f.write(
            public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
        )

if not os.path.exists("private.pem") or not os.path.exists("public.pem"):
    generate_keys()

with open("private.pem", "r") as f:
    PRIVATE_KEY = f.read()
with open("public.pem", "r") as f:
    PUBLIC_KEY = f.read()

# --- URL pública (variable de entorno para hosting) ---
PUBLIC_URL = os.environ.get("PUBLIC_URL", "https://Final_EsteroRock.up.railway.app")

# --- Crear PDF con QR ---
def create_certificate_pdf(name, course, date, link_or_token, output_file):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    logo_path = "static/logo.png"
    if os.path.exists(logo_path):
        c.drawImage(logo_path, 40, 500, width=100, height=100, mask="auto")
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(420, 520, "CERTIFICADO DIGITAL")
    c.setFont("Helvetica", 18)
    c.drawCentredString(420, 460, f"Se certifica que {name}")
    c.drawCentredString(420, 430, f"ha completado el curso {course}")
    c.drawCentredString(420, 400, f"Fecha: {date}")
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=6, border=4)
    qr.add_data(link_or_token)
    qr.make(fit=True)
    img_qr = qr.make_image(fill_color="black", back_color="white")
    qr_buffer = BytesIO()
    img_qr.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    qr_image = Image.open(qr_buffer)
    c.drawInlineImage(qr_image, 720, 50, 3.5*cm, 3.5*cm)
    c.setFont("Helvetica-Oblique", 12)
    c.drawCentredString(420, 100, "Firmado digitalmente por:")
    c.drawCentredString(420, 80, "Darlin Gallardo, Bryan Serrano, Adalberto Moncada, Lenin Gallardo")
    c.showPage()
    c.save()
    buffer.seek(0)
    with open(output_file, "wb") as f:
        f.write(buffer.read())

# --- Rutas Flask ---
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/generar", methods=["POST"])
def generar():
    name = request.form["name"]
    course = request.form["course"]
    date = request.form["date"]
    payload = {
        "cert_id": str(uuid.uuid4()),
        "name": name,
        "course": course,
        "date": date,
        "issuer": "Mi Academia",
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=365),
    }
    token = jwt.encode(payload, PRIVATE_KEY, algorithm="RS256")
    filename = f"certificado_{name.replace(' ', '_')}.pdf"
    filepath = os.path.join(GENERATED_FILES_DIR, filename)
    qr_link = f"{PUBLIC_URL}/verificar?token={token}"
    create_certificate_pdf(name, course, date, qr_link, filepath)
    qr_img = qrcode.make(qr_link)
    buffered = BytesIO()
    qr_img.save(buffered, format="PNG")
    qr_base64 = base64.b64encode(buffered.getvalue()).decode()
    return render_template(
        "confirmacion.html",
        name=name,
        filename=filename,
        qr_base64=qr_base64
    )

@app.route("/descargar/<filename>")
def descargar_certificado(filename):
    filepath = os.path.join(GENERATED_FILES_DIR, filename)
    return send_file(filepath, as_attachment=True)

@app.route("/verificar")
def verificar():
    token = request.args.get("token")
    try:
        payload = jwt.decode(token, PUBLIC_KEY, algorithms=["RS256"])
        return render_template("verificar.html", valid=True, payload=payload)
    except jwt.ExpiredSignatureError:
        return render_template("verificar.html", valid=False, reason="expired")
    except jwt.InvalidTokenError:
        return render_template("verificar.html", valid=False, reason="invalid")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(host="0.0.0.0", port=port, debug=True)
