import io
import re
import zipfile
import streamlit as st
import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageOps, ImageEnhance
import pytesseract

# ==========================================
# CONFIG
# ==========================================
APP_TITLE = "📄 Suite PDF: Unir, Convertir Imágenes, Firmar y Comprimir"
TARGET_DEFAULT = "Lennin Karina Triana Fandiño"

# Color aguamarina
ACCENT = "#20DE6E"
ACCENT_HOVER = "#16B85B"

st.set_page_config(page_title="Suite PDF", page_icon="📄", layout="wide")

# ==========================================
# STYLES (pro)
# ==========================================
st.markdown(
    f"""
    <style>
      .stApp {{
        background: radial-gradient(1200px 700px at 10% 10%, #F2FFFA 0%, #EFFFF7 35%, #F7FFFB 70%, #FFFFFF 100%);
      }}

      section[data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #EFFFF7 0%, #E8FFF1 100%);
        border-right: 1px solid #C9F7DE;
      }}

      h1, h2, h3 {{
        color: #0F5132;
      }}

      .hero {{
        background: linear-gradient(90deg, {ACCENT} 0%, #8CF0C0 100%);
        border: 1px solid #BDF3D4;
        padding: 18px 22px;
        border-radius: 18px;
        font-weight: 900;
        color: #063B22;
        text-align: center;
        font-size: 28px;
        box-shadow: 0 10px 30px rgba(32, 222, 110, 0.18);
        margin-bottom: 16px;
      }}

      .card {{
        background: #FFFFFF;
        border: 1px solid #C9F7DE;
        border-radius: 16px;
        padding: 16px 16px;
        box-shadow: 0 6px 18px rgba(15, 81, 50, 0.07);
        margin-bottom: 12px;
      }}

      .muted {{
        color: #3D6B55;
        font-size: 14px;
      }}

      div[data-testid="stButton"] > button,
      div[data-testid="stDownloadButton"] > button {{
        background-color: {ACCENT};
        color: #05311D;
        border: none;
        border-radius: 12px;
        padding: 0.60rem 1rem;
        font-weight: 900;
      }}

      div[data-testid="stButton"] > button:hover,
      div[data-testid="stDownloadButton"] > button:hover {{
        background-color: {ACCENT_HOVER};
        color: white;
      }}

      .stRadio > label, .stCheckbox > label {{
        font-weight: 600 !important;
      }}

      .block-container {{
        padding-top: 1.2rem;
        padding-bottom: 2rem;
      }}
    </style>
    """,
    unsafe_allow_html=True
)

# ==========================================
# SESSION STATE
# ==========================================
def init_state():
    defaults = {
        # Merge & sign
        "merge_files": [],            # [{"name": str, "bytes": bytes, "size": int}]
        "merge_signature": None,      # signature of set of files to detect changes
        "merged_pdf_bytes": None,

        # detection
        "detected": False,
        "det_page": None,
        "det_rect": None,            # (x0,y0,x1,y1)
        "det_method": None,

        # inputs
        "last_output_name": "PDF_unido.pdf",
        "last_target": TARGET_DEFAULT,

        # signature offsets
        "sig_dx": 0.0,
        "sig_dy": 0.0,

        # Images module
        "converted_images_pdf_bytes": [],
        "converted_images_names": [],
        "merged_images_pdf_bytes": None,

        # Compress module
        "compressed_pdf_bytes": None,
        "compressed_name": "archivo_comprimido.pdf",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def reset_merge():
    st.session_state.merge_files = []
    st.session_state.merge_signature = None
    st.session_state.merged_pdf_bytes = None
    st.session_state.detected = False
    st.session_state.det_page = None
    st.session_state.det_rect = None
    st.session_state.det_method = None
    st.session_state.sig_dx = 0.0
    st.session_state.sig_dy = 0.0

def reset_images():
    st.session_state.converted_images_pdf_bytes = []
    st.session_state.converted_images_names = []
    st.session_state.merged_images_pdf_bytes = None

def reset_compress():
    st.session_state.compressed_pdf_bytes = None
    st.session_state.compressed_name = "archivo_comprimido.pdf"

init_state()

# ==========================================
# UTILITIES
# ==========================================
def normalize(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s

def merge_pdfs(files_bytes_in_order) -> bytes:
    merged = fitz.open()
    for b in files_bytes_in_order:
        src = fitz.open(stream=b, filetype="pdf")
        merged.insert_pdf(src)
        src.close()
    out = io.BytesIO()
    merged.save(out)
    merged.close()
    out.seek(0)
    return out.getvalue()

def find_name_rect_text(doc: fitz.Document, target_text: str):
    for pi in range(doc.page_count):
        page = doc[pi]
        rects = page.search_for(target_text)
        if rects:
            return pi, rects[0]
    return None

def ocr_find_name_rect(doc: fitz.Document, target_text: str, zoom=2.8):
    target_text = (target_text or "").strip()
    if not target_text:
        return None

    target_tokens = normalize(target_text).split()
    if not target_tokens:
        return None

    for pi in range(doc.page_count):
        page = doc[pi]
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

        words = []
        for i in range(len(data["text"])):
            txt = normalize(data["text"][i])
            if not txt:
                continue
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            words.append((txt, x, y, x + w, y + h))

        for start in range(0, len(words) - len(target_tokens) + 1):
            ok = True
            for j, tok in enumerate(target_tokens):
                if words[start + j][0] != tok:
                    ok = False
                    break
            if ok:
                x0 = min(words[start + j][1] for j in range(len(target_tokens)))
                y0 = min(words[start + j][2] for j in range(len(target_tokens)))
                x1 = max(words[start + j][3] for j in range(len(target_tokens)))
                y1 = max(words[start + j][4] for j in range(len(target_tokens)))

                page_rect = page.rect
                sx = page_rect.width / pix.width
                sy = page_rect.height / pix.height
                rect_pdf = fitz.Rect(x0 * sx, y0 * sy, x1 * sx, y1 * sy)
                return pi, rect_pdf

    return None

def render_page_image(page: fitz.Page, zoom=2.0) -> Image.Image:
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

def rect_pdf_to_img(rect_pdf: fitz.Rect, zoom: float):
    return (
        int(rect_pdf.x0 * zoom),
        int(rect_pdf.y0 * zoom),
        int(rect_pdf.x1 * zoom),
        int(rect_pdf.y1 * zoom),
    )

def draw_highlight(img: Image.Image, rect_img, outline_width=5) -> Image.Image:
    out = img.copy()
    d = ImageDraw.Draw(out)
    d.rectangle(rect_img, outline="red", width=outline_width)
    return out

def draw_signature_preview_above(
    img: Image.Image,
    rect_pdf: fitz.Rect,
    sig_img: Image.Image,
    zoom: float,
    gap=10,
    pad=6,
    scale_w=1.4,
    scale_h=2.0,
    dx_pdf=0.0,
    dy_pdf=0.0,
) -> Image.Image:
    out = img.copy()

    nx0, ny0, nx1, ny1 = rect_pdf_to_img(rect_pdf, zoom)
    name_w = max(1, nx1 - nx0)
    name_h = max(1, ny1 - ny0)

    fw = int(name_w * scale_w) + pad * 2
    fh = int(name_h * scale_h) + pad * 2

    cx = (nx0 + nx1) // 2
    fx0 = cx - fw // 2
    fy0 = ny0 - gap - fh

    dx_px = int(dx_pdf * zoom)
    dy_px = int(dy_pdf * zoom)
    fx0 += dx_px
    fy0 += dy_px

    fx0 = max(0, min(fx0, out.width - 1))
    fy0 = max(0, min(fy0, out.height - 1))

    fx1 = min(out.width, fx0 + fw)
    fy1 = min(out.height, fy0 + fh)

    w = max(1, fx1 - fx0)
    h = max(1, fy1 - fy0)

    sig = sig_img.convert("RGBA").resize((w, h))
    out.paste(sig, (fx0, fy0), sig)
    return out

def insert_signature_above_into_pdf(
    doc: fitz.Document,
    page_index: int,
    name_rect: fitz.Rect,
    sig_bytes: bytes,
    gap=6,
    pad=4,
    scale_w=1.4,
    scale_h=2.0,
    dx_pdf=0.0,
    dy_pdf=0.0,
):
    page = doc[page_index]

    name_w = name_rect.x1 - name_rect.x0
    name_h = name_rect.y1 - name_rect.y0

    w = name_w * scale_w + pad * 2
    h = name_h * scale_h + pad * 2

    cx = (name_rect.x0 + name_rect.x1) / 2
    x0 = cx - w / 2
    x1 = cx + w / 2

    y1 = name_rect.y0 - gap
    y0 = y1 - h

    x0 += dx_pdf
    x1 += dx_pdf
    y0 += dy_pdf
    y1 += dy_pdf

    if y0 < 0:
        y0 = 0
        y1 = h

    rect_sig = fitz.Rect(x0, y0, x1, y1)
    page.insert_image(rect_sig, stream=sig_bytes, overlay=True)

# ==========================================
# IMAGES → PDF
# ==========================================
def open_uploaded_image(uploaded_image) -> Image.Image:
    img = Image.open(io.BytesIO(uploaded_image.getvalue()))
    img = ImageOps.exif_transpose(img)
    return img

def preprocess_image(img: Image.Image, auto_enhance=False,
                     brightness=1.0, contrast=1.0, sharpness=1.0,
                     grayscale=False, black_white=False) -> Image.Image:
    img = img.copy()
    if img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGB")

    if auto_enhance:
        temp = img.convert("RGB") if img.mode == "RGBA" else img.copy()
        temp = ImageOps.autocontrast(temp)
        temp = ImageEnhance.Contrast(temp).enhance(1.2)
        temp = ImageEnhance.Sharpness(temp).enhance(1.3)
        img = temp

    work = img.convert("RGB") if img.mode == "RGBA" else img.copy()
    work = ImageEnhance.Brightness(work).enhance(brightness)
    work = ImageEnhance.Contrast(work).enhance(contrast)
    work = ImageEnhance.Sharpness(work).enhance(sharpness)

    if grayscale:
        work = ImageOps.grayscale(work)

    if black_white:
        gray = ImageOps.grayscale(work)
        work = gray.point(lambda x: 255 if x > 160 else 0, mode="1").convert("RGB")
    else:
        if work.mode != "RGB":
            work = work.convert("RGB")

    return work

def pil_image_to_pdf_bytes(img: Image.Image) -> bytes:
    img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, format="PDF", resolution=150.0)
    out.seek(0)
    return out.getvalue()

def convert_multiple_images_to_individual_pdfs(uploaded_images, auto_enhance=False,
                                               brightness=1.0, contrast=1.0, sharpness=1.0,
                                               grayscale=False, black_white=False):
    pdfs, names = [], []
    for img_file in uploaded_images:
        img = open_uploaded_image(img_file)
        img = preprocess_image(img, auto_enhance, brightness, contrast, sharpness, grayscale, black_white)
        pdf_bytes = pil_image_to_pdf_bytes(img)
        base_name = img_file.name.rsplit(".", 1)[0]
        names.append(f"{base_name}.pdf")
        pdfs.append(pdf_bytes)
    return pdfs, names

def build_zip_of_pdfs(pdf_bytes_list, pdf_names):
    out_zip = io.BytesIO()
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for b, n in zip(pdf_bytes_list, pdf_names):
            zf.writestr(n, b)
    out_zip.seek(0)
    return out_zip.getvalue()

# ==========================================
# COMPRESS PDF
# ==========================================
def guess_file_type(filename: str) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return "pdf"
    if name.endswith(".jpg") or name.endswith(".jpeg") or name.endswith(".png"):
        return "image"
    return "unknown"

def compress_pdf_soft(pdf_bytes: bytes) -> bytes:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out = io.BytesIO()
    doc.save(out, garbage=4, deflate=True, clean=True)
    doc.close()
    out.seek(0)
    return out.getvalue()

def compress_pdf_rasterize(pdf_bytes: bytes, dpi: int = 120, jpeg_quality: int = 60) -> bytes:
    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    dst = fitz.open()
    zoom = dpi / 72.0

    for i in range(src.page_count):
        page = src[i]
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="JPEG", quality=jpeg_quality, optimize=True)
        img_bytes = img_bytes.getvalue()

        rect = page.rect
        new_page = dst.new_page(width=rect.width, height=rect.height)
        new_page.insert_image(rect, stream=img_bytes)

    out = io.BytesIO()
    dst.save(out, garbage=4, deflate=True, clean=True)
    dst.close()
    src.close()
    out.seek(0)
    return out.getvalue()

# ==========================================
# SIDEBAR
# ==========================================
st.sidebar.title("📚 Menú")
menu = st.sidebar.radio(
    "Selecciona una herramienta",
    ["Inicio", "Unir PDFs y firmar", "Imágenes a PDF", "Comprimir PDF"],
)

st.sidebar.markdown("---")
st.sidebar.caption("Herramientas pensadas para una experiencia simple, rápida y bonita ✨")

# ==========================================
# INICIO
# ==========================================
if menu == "Inicio":
    st.markdown('<div class="hero">Aplicativo en construcción para Karina 💓</div>', unsafe_allow_html=True)
    st.markdown(f"<div class='card'><h2 style='margin:0'>{APP_TITLE}</h2>"
                f"<p class='muted'>Unir PDFs • Firmar con OCR • Convertir imágenes • Comprimir archivos</p></div>",
                unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("<div class='card'><h3>📄 Unir PDFs</h3>"
                    "<p class='muted'>Respeta el orden del usuario, reordena con flechas y elimina archivos.</p></div>",
                    unsafe_allow_html=True)
    with c2:
        st.markdown("<div class='card'><h3>✍️ Firma opcional</h3>"
                    "<p class='muted'>Detecta nombre por texto u OCR si es escaneado. Preview + mover firma.</p></div>",
                    unsafe_allow_html=True)
    with c3:
        st.markdown("<div class='card'><h3>🗜️ Comprimir</h3>"
                    "<p class='muted'>Reduce tamaño con modo rápido o suave y descarga el PDF comprimido.</p></div>",
                    unsafe_allow_html=True)

# ==========================================
# UNIR PDFs Y FIRMAR
# ==========================================
elif menu == "Unir PDFs y firmar":
    st.markdown("<div class='card'><h2 style='margin:0'>📄 Unir PDFs y firmar</h2>"
                "<p class='muted'>El orden final será el que veas en “Orden actual de unión”.</p></div>",
                unsafe_allow_html=True)

    top1, top2, top3 = st.columns([1, 1, 2])
    with top1:
        if st.button("🔄 Reiniciar sección"):
            reset_merge()
            st.rerun()
    with top2:
        enable_ocr = st.toggle("Usar OCR si viene escaneado", value=True, key="enable_ocr")
    with top3:
        st.session_state.last_target = st.text_input(
            "Nombre a detectar (para habilitar firma)",
            value=st.session_state.last_target,
            key="target_name"
        )

    st.session_state.last_output_name = st.text_input(
        "Nombre del PDF final",
        value=st.session_state.last_output_name,
        key="output_name"
    )

    # Input de PDFs
    uploaded_files = st.file_uploader(
        "Sube tus PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        key="pdfs_uploader"
    )

    # Sync inteligente: solo si cambia el conjunto (no el orden)
    if uploaded_files:
        incoming_items = [(f.name, len(f.getvalue())) for f in uploaded_files]
        incoming_signature = tuple(sorted(incoming_items))
        if st.session_state.merge_signature != incoming_signature:
            st.session_state.merge_files = [
                {"name": f.name, "bytes": f.getvalue(), "size": len(f.getvalue())} for f in uploaded_files
            ]
            st.session_state.merge_signature = incoming_signature

    # Botón manual para volver al orden del explorador
    if uploaded_files and st.button("↩️ Sincronizar con selección del explorador"):
        st.session_state.merge_files = [
            {"name": f.name, "bytes": f.getvalue(), "size": len(f.getvalue())} for f in uploaded_files
        ]
        st.rerun()

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("🧾 Orden actual de unión")

    if st.session_state.merge_files:
        a1, a2, a3, a4 = st.columns([1, 1, 1, 1])
        with a1:
            if st.button("A→Z (ordenar por nombre)"):
                st.session_state.merge_files = sorted(st.session_state.merge_files, key=lambda x: x["name"].lower())
                st.rerun()
        with a2:
            if st.button("🔁 Invertir orden"):
                st.session_state.merge_files = list(reversed(st.session_state.merge_files))
                st.rerun()
        with a3:
            if st.button("🧹 Limpiar lista"):
                st.session_state.merge_files = []
                st.rerun()
        with a4:
            st.caption(f"{len(st.session_state.merge_files)} archivo(s)")

        for i, item in enumerate(st.session_state.merge_files):
            c1, c2, c3, c4 = st.columns([7, 1, 1, 1])
            with c1:
                mb = item["size"] / (1024 * 1024)
                st.write(f"**{i+1}.** {item['name']}  ·  {mb:.2f} MB")
            with c2:
                if st.button("⬆️", key=f"up_{i}") and i > 0:
                    st.session_state.merge_files[i-1], st.session_state.merge_files[i] = (
                        st.session_state.merge_files[i],
                        st.session_state.merge_files[i-1],
                    )
                    st.rerun()
            with c3:
                if st.button("⬇️", key=f"down_{i}") and i < len(st.session_state.merge_files) - 1:
                    st.session_state.merge_files[i+1], st.session_state.merge_files[i] = (
                        st.session_state.merge_files[i],
                        st.session_state.merge_files[i+1],
                    )
                    st.rerun()
            with c4:
                if st.button("🗑️", key=f"del_{i}"):
                    st.session_state.merge_files.pop(i)
                    st.rerun()
    else:
        st.info("Carga tus PDFs para armar la lista de unión.")

    st.markdown("</div>", unsafe_allow_html=True)

    # Unir PDFs
    can_merge = len(st.session_state.merge_files) >= 1
    if st.button("✅ Unir PDFs", disabled=not can_merge, key="merge_btn"):
        st.session_state.sig_dx = 0.0
        st.session_state.sig_dy = 0.0

        files_bytes = [x["bytes"] for x in st.session_state.merge_files]
        with st.spinner("Uniendo PDFs..."):
            merged_bytes = merge_pdfs(files_bytes)

        st.session_state.merged_pdf_bytes = merged_bytes

        # ---- detección segura (NO falla si target está vacío)
        target = (st.session_state.last_target or "").strip()

        doc = fitz.open(stream=merged_bytes, filetype="pdf")
        found = None
        method = None

        if target:
            found = find_name_rect_text(doc, target)
            method = "texto"
            if (not found) and enable_ocr:
                method = "ocr"
                with st.spinner("Intentando OCR..."):
                    found_ocr = ocr_find_name_rect(doc, target, zoom=2.8)
                if found_ocr:
                    found = found_ocr

        if found:
            page_index, rect = found
            st.session_state.detected = True
            st.session_state.det_page = int(page_index)
            st.session_state.det_rect = (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))
            st.session_state.det_method = method
        else:
            st.session_state.detected = False
            st.session_state.det_page = None
            st.session_state.det_rect = None
            st.session_state.det_method = None

        doc.close()
        st.success("PDFs unidos correctamente ✅")

    # Descarga + firma
    if st.session_state.merged_pdf_bytes:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("⬇️ Descarga y firma opcional")

        outname = st.session_state.last_output_name
        outname = outname if outname.lower().endswith(".pdf") else outname + ".pdf"

        st.download_button(
            "Descargar PDF unido (sin firma)",
            data=st.session_state.merged_pdf_bytes,
            file_name=outname,
            mime="application/pdf",
            key="dl_merged"
        )

        target = (st.session_state.last_target or "").strip()
        if not target:
            st.info("💡 Para habilitar firma, escribe el **Nombre a detectar**. Si lo dejas vacío, solo se une el PDF.")
        elif not st.session_state.detected:
            st.info("No se detectó el nombre configurado en el PDF unido (ni por texto ni por OCR).")
        else:
            st.success(f"Nombre detectado ✅ Método: {st.session_state.det_method} | Página: {st.session_state.det_page + 1}")

            preview_zoom = st.slider("Zoom previsualización", 1.0, 3.5, 2.0, 0.1, key="preview_zoom")

            doc = fitz.open(stream=st.session_state.merged_pdf_bytes, filetype="pdf")
            page = doc[st.session_state.det_page]
            rect_pdf = fitz.Rect(*st.session_state.det_rect)

            img_page = render_page_image(page, zoom=preview_zoom)
            rect_img = rect_pdf_to_img(rect_pdf, zoom=preview_zoom)
            st.image(draw_highlight(img_page, rect_img), caption="Nombre detectado", use_container_width=True)

            wants_sign = st.toggle("¿Deseas firmar este documento?", value=False, key="wants_sign")
            if wants_sign:
                sig_file = st.file_uploader("Sube la firma (PNG/JPG)", type=["png", "jpg", "jpeg"], key="sig_uploader")

                gap = st.slider("Espacio entre firma y nombre", 0, 40, 10, key="gap")
                pad = st.slider("Margen", 0, 20, 6, key="pad")
                scale_w = st.slider("Escala ancho firma", 0.8, 2.5, 1.4, 0.1, key="scale_w")
                scale_h = st.slider("Escala alto firma", 0.8, 4.0, 2.0, 0.1, key="scale_h")

                st.markdown("#### Mover firma (flechas)")
                step = st.slider("Paso de movimiento", 1, 30, 6, key="move_step")

                c1, c2, c3, c4, c5 = st.columns(5)
                with c1:
                    if st.button("⬅️", key="btn_left"):
                        st.session_state.sig_dx -= float(step)
                with c2:
                    if st.button("➡️", key="btn_right"):
                        st.session_state.sig_dx += float(step)
                with c3:
                    if st.button("⬆️", key="btn_up"):
                        st.session_state.sig_dy -= float(step)
                with c4:
                    if st.button("⬇️", key="btn_down"):
                        st.session_state.sig_dy += float(step)
                with c5:
                    if st.button("Reset", key="btn_reset_move"):
                        st.session_state.sig_dx = 0.0
                        st.session_state.sig_dy = 0.0

                st.caption(f"dx={st.session_state.sig_dx} | dy={st.session_state.sig_dy}")

                if sig_file:
                    sig_img = Image.open(sig_file).convert("RGBA")
                    preview_with_sig = draw_signature_preview_above(
                        img_page, rect_pdf, sig_img,
                        zoom=preview_zoom,
                        gap=gap, pad=pad, scale_w=scale_w, scale_h=scale_h,
                        dx_pdf=st.session_state.sig_dx, dy_pdf=st.session_state.sig_dy,
                    )
                    st.image(preview_with_sig, caption="Previsualización con firma", use_container_width=True)

                    if st.button("🔒 Confirmar y generar PDF firmado", type="primary", key="confirm_sign"):
                        doc2 = fitz.open(stream=st.session_state.merged_pdf_bytes, filetype="pdf")
                        rect_pdf2 = fitz.Rect(*st.session_state.det_rect)

                        insert_signature_above_into_pdf(
                            doc2,
                            st.session_state.det_page,
                            rect_pdf2,
                            sig_file.getvalue(),
                            gap=max(0, int(gap / preview_zoom)),
                            pad=pad,
                            scale_w=scale_w,
                            scale_h=scale_h,
                            dx_pdf=st.session_state.sig_dx,
                            dy_pdf=st.session_state.sig_dy,
                        )

                        out = io.BytesIO()
                        doc2.save(out)
                        doc2.close()
                        out.seek(0)

                        st.download_button(
                            "Descargar PDF unido y firmado",
                            data=out,
                            file_name="PDF_unido_firmado.pdf",
                            mime="application/pdf",
                            key="dl_signed"
                        )
            doc.close()

        st.markdown("</div>", unsafe_allow_html=True)

# ==========================================
# IMÁGENES A PDF
# ==========================================
elif menu == "Imágenes a PDF":
    st.markdown("<div class='card'><h2 style='margin:0'>🖼️ Imágenes a PDF</h2>"
                "<p class='muted'>Mejora la imagen antes de convertir y descarga individual o unificado.</p></div>",
                unsafe_allow_html=True)

    if st.button("🔄 Reiniciar sección imágenes"):
        reset_images()
        st.rerun()

    uploaded_images = st.file_uploader(
        "Sube una o varias imágenes",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
        key="images_uploader"
    )

    if uploaded_images:
        selected_preview = st.selectbox(
            "Imagen para previsualizar",
            options=list(range(len(uploaded_images))),
            format_func=lambda i: uploaded_images[i].name,
            key="selected_preview_img"
        )

        original_img = open_uploaded_image(uploaded_images[selected_preview])

        auto_enhance = st.toggle("Mejora automática", value=True, key="auto_enhance")

        c1, c2, c3 = st.columns(3)
        with c1:
            brightness = st.slider("Brillo", 0.5, 2.0, 1.0, 0.1, key="brightness")
        with c2:
            contrast = st.slider("Contraste", 0.5, 2.5, 1.2, 0.1, key="contrast")
        with c3:
            sharpness = st.slider("Nitidez", 0.5, 3.0, 1.2, 0.1, key="sharpness")

        c4, c5 = st.columns(2)
        with c4:
            grayscale = st.checkbox("Escala de grises", key="grayscale")
        with c5:
            black_white = st.checkbox("Blanco y negro", key="black_white")

        improved_img = preprocess_image(
            original_img, auto_enhance, brightness, contrast, sharpness, grayscale, black_white
        )

        p1, p2 = st.columns(2)
        with p1:
            st.image(original_img, caption="Original", use_container_width=True)
        with p2:
            st.image(improved_img, caption="Mejorada", use_container_width=True)

        mode = st.radio(
            "¿Qué deseas hacer?",
            ["Convertir y descargar PDFs individuales", "Convertir y unificar en un solo PDF", "Hacer ambas opciones"],
            key="images_mode"
        )

        if st.button("🖼️ Convertir imágenes", key="convert_images_btn"):
            with st.spinner("Convirtiendo..."):
                pdfs, pdf_names = convert_multiple_images_to_individual_pdfs(
                    uploaded_images, auto_enhance, brightness, contrast, sharpness, grayscale, black_white
                )

            st.session_state.converted_images_pdf_bytes = pdfs
            st.session_state.converted_images_names = pdf_names

            if mode in ["Convertir y unificar en un solo PDF", "Hacer ambas opciones"]:
                st.session_state.merged_images_pdf_bytes = merge_pdfs(pdfs)
            else:
                st.session_state.merged_images_pdf_bytes = None

            st.success("Conversión completada ✅")

    if st.session_state.converted_images_pdf_bytes:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("⬇️ Descargas")

        mode = st.session_state.get("images_mode", "Convertir y descargar PDFs individuales")

        if mode in ["Convertir y descargar PDFs individuales", "Hacer ambas opciones"]:
            zip_bytes = build_zip_of_pdfs(
                st.session_state.converted_images_pdf_bytes,
                st.session_state.converted_images_names
            )
            st.download_button(
                "Descargar ZIP (PDFs individuales)",
                data=zip_bytes,
                file_name="imagenes_convertidas_pdf.zip",
                mime="application/zip",
                key="download_zip_individuals"
            )

        if mode in ["Convertir y unificar en un solo PDF", "Hacer ambas opciones"]:
            if st.session_state.merged_images_pdf_bytes:
                st.download_button(
                    "Descargar PDF unificado",
                    data=st.session_state.merged_images_pdf_bytes,
                    file_name="imagenes_unificadas.pdf",
                    mime="application/pdf",
                    key="download_merged_images_pdf"
                )

        st.markdown("</div>", unsafe_allow_html=True)

# ==========================================
# COMPRIMIR PDF
# ==========================================
elif menu == "Comprimir PDF":
    st.markdown("<div class='card'><h2 style='margin:0'>🗜️ Comprimir PDF</h2>"
                "<p class='muted'>Modo rápido reduce mucho (ideal escaneados). Modo suave mantiene mejor calidad.</p></div>",
                unsafe_allow_html=True)

    if st.button("🔄 Reiniciar compresión"):
        reset_compress()
        st.rerun()

    up = st.file_uploader("Sube tu archivo", type=["pdf", "jpg", "jpeg", "png"], key="compress_uploader")
    if up:
        ftype = guess_file_type(up.name)
        st.info(f"Tipo detectado: {ftype.upper()}")

        if ftype != "pdf":
            st.warning("Este módulo comprime PDFs. Si subiste imagen, usa Imágenes a PDF.")
        else:
            original_bytes = up.getvalue()
            original_mb = len(original_bytes) / (1024 * 1024)
            st.write(f"Tamaño original: **{original_mb:.2f} MB**")

            mode = st.radio(
                "Modo",
                ["Rápido (reduce mucho)", "Suave (reduce poco, conserva mejor)"],
                index=0,
                key="compress_mode"
            )

            if mode.startswith("Rápido"):
                dpi = st.select_slider("Calidad (DPI)", options=[72, 96, 120, 150], value=120, key="dpi")
                quality = st.select_slider("Calidad JPEG", options=[35, 45, 60, 75], value=60, key="jpg_quality")
            else:
                dpi, quality = None, None

            out_name = st.text_input("Nombre del PDF comprimido", value="archivo_comprimido.pdf", key="compress_outname")

            if st.button("🗜️ Comprimir ahora", type="primary", key="do_compress"):
                with st.spinner("Comprimiendo..."):
                    if mode.startswith("Rápido"):
                        compressed = compress_pdf_rasterize(original_bytes, dpi=int(dpi), jpeg_quality=int(quality))
                    else:
                        compressed = compress_pdf_soft(original_bytes)

                st.session_state.compressed_pdf_bytes = compressed
                st.session_state.compressed_name = out_name if out_name.lower().endswith(".pdf") else out_name + ".pdf"

                new_mb = len(compressed) / (1024 * 1024)
                reduction = (1 - (new_mb / original_mb)) * 100 if original_mb > 0 else 0
                st.success(f"Listo ✅ Nuevo tamaño: **{new_mb:.2f} MB** | Reducción aprox: **{reduction:.1f}%**")

    if st.session_state.compressed_pdf_bytes:
        st.download_button(
            "Descargar PDF comprimido",
            data=st.session_state.compressed_pdf_bytes,
            file_name=st.session_state.compressed_name,
            mime="application/pdf",
            key="download_compressed"
        )
