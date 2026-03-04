import io
import re
import zipfile
import streamlit as st
import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageOps
import pytesseract

# ============================
# CONFIG GENERAL
# ============================
APP_TITLE = "📄 Unir PDFs + 🖼️ Convertir JPG a PDF + ✍️ Firma opcional"
TARGET_DEFAULT = "Lennin Karina Triana Fandiño"
ACCENT_COLOR = "#C384E8"

st.set_page_config(
    page_title="PDF Merger & Image to PDF",
    page_icon="📄",
    layout="wide"
)

# ============================
# ESTILOS
# ============================
st.markdown(
    f"""
    <style>
    .stApp {{
        background-color: #F8F2FF;
    }}

    h1, h2, h3 {{
        color: #5B2A86;
    }}

    div[data-testid="stButton"] > button {{
        background-color: {ACCENT_COLOR};
        color: white;
        border: none;
        border-radius: 10px;
        padding: 0.6rem 1rem;
        font-weight: 600;
    }}

    div[data-testid="stDownloadButton"] > button {{
        background-color: {ACCENT_COLOR};
        color: white;
        border: none;
        border-radius: 10px;
        padding: 0.6rem 1rem;
        font-weight: 600;
    }}

    div[data-baseweb="tag"] {{
        background-color: #E9D7FA !important;
    }}

    .block-container {{
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }}

    .custom-box {{
        background: white;
        padding: 1rem;
        border-radius: 14px;
        border: 1px solid #E7D8F8;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        margin-bottom: 1rem;
    }}
    </style>
    """,
    unsafe_allow_html=True
)

# ============================
# SESSION STATE
# ============================
def init_state():
    defaults = {
        "merged_pdf_bytes": None,
        "detected": False,
        "det_page": None,
        "det_rect": None,
        "det_method": None,
        "last_output_name": "PDF_unido.pdf",
        "last_target": TARGET_DEFAULT,
        "sig_dx": 0.0,
        "sig_dy": 0.0,
        "converted_images_pdf_bytes": [],
        "converted_images_names": [],
        "merged_images_pdf_bytes": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def reset_pdf_section():
    st.session_state.merged_pdf_bytes = None
    st.session_state.detected = False
    st.session_state.det_page = None
    st.session_state.det_rect = None
    st.session_state.det_method = None
    st.session_state.sig_dx = 0.0
    st.session_state.sig_dy = 0.0


def reset_images_section():
    st.session_state.converted_images_pdf_bytes = []
    st.session_state.converted_images_names = []
    st.session_state.merged_images_pdf_bytes = None


init_state()

# ============================
# HELPERS PDF
# ============================
def normalize(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def merge_pdfs(files_bytes_in_order) -> bytes:
    merged = fitz.open()
    for pdf_bytes in files_bytes_in_order:
        src = fitz.open(stream=pdf_bytes, filetype="pdf")
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
    target_tokens = normalize(target_text).split()

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


# ============================
# HELPERS IMÁGENES -> PDF
# ============================
def image_file_to_pdf_bytes(uploaded_image) -> bytes:
    img = Image.open(io.BytesIO(uploaded_image.getvalue()))
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", img.size, "white")
        if img.mode == "P":
            img = img.convert("RGBA")
        background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
        img = background
    else:
        img = img.convert("RGB")

    out = io.BytesIO()
    img.save(out, format="PDF", resolution=100.0)
    out.seek(0)
    return out.getvalue()


def convert_multiple_images_to_individual_pdfs(uploaded_images):
    pdfs = []
    names = []

    for img_file in uploaded_images:
        pdf_bytes = image_file_to_pdf_bytes(img_file)
        base_name = img_file.name.rsplit(".", 1)[0]
        pdf_name = f"{base_name}.pdf"
        pdfs.append(pdf_bytes)
        names.append(pdf_name)

    return pdfs, names


def merge_image_pdfs(pdf_bytes_list) -> bytes:
    return merge_pdfs(pdf_bytes_list)


def build_zip_of_pdfs(pdf_bytes_list, pdf_names):
    out_zip = io.BytesIO()
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for pdf_bytes, pdf_name in zip(pdf_bytes_list, pdf_names):
            zf.writestr(pdf_name, pdf_bytes)
    out_zip.seek(0)
    return out_zip.getvalue()


# ============================
# UI
# ============================
st.title(APP_TITLE)
st.write("Aquí puedes trabajar con PDFs e imágenes en un solo lugar.")

tab1, tab2 = st.tabs(["📄 Unir PDFs y firmar", "🖼️ Convertir JPG/JPEG/PNG a PDF"])

# =========================================================
# TAB 1: PDF MERGE + FIRMA
# =========================================================
with tab1:
    st.markdown('<div class="custom-box">', unsafe_allow_html=True)
    st.subheader("Unir PDFs")

    left_top, right_top = st.columns([1, 1])
    with left_top:
        if st.button("🔄 Reiniciar sección PDF"):
            reset_pdf_section()
    with right_top:
        enable_ocr = st.toggle("Usar OCR si viene escaneado", value=True, key="enable_ocr")

    uploaded_files = st.file_uploader(
        "Sube tus PDFs en el orden que quieres unirlos",
        type=["pdf"],
        accept_multiple_files=True,
        key="pdfs_uploader"
    )

    target_name = st.text_input(
        "Nombre a detectar para habilitar firma",
        value=st.session_state.last_target,
        key="target_name"
    )

    output_name = st.text_input(
        "Nombre del PDF final",
        value=st.session_state.last_output_name,
        key="output_name"
    )

    st.session_state.last_target = target_name
    st.session_state.last_output_name = output_name if output_name else "PDF_unido.pdf"

    if uploaded_files:
        st.write("**Archivos cargados:**")
        for i, f in enumerate(uploaded_files, start=1):
            st.write(f"{i}. {f.name}")

        if st.button("✅ Unir PDFs", key="merge_btn"):
            st.session_state.sig_dx = 0.0
            st.session_state.sig_dy = 0.0

            files_bytes = [f.getvalue() for f in uploaded_files]

            with st.spinner("Uniendo PDFs..."):
                merged_bytes = merge_pdfs(files_bytes)

            st.session_state.merged_pdf_bytes = merged_bytes

            doc = fitz.open(stream=merged_bytes, filetype="pdf")

            found = find_name_rect_text(doc, target_name)
            method = "texto"

            if not found and enable_ocr:
                method = "ocr"
                with st.spinner("Intentando OCR..."):
                    found_ocr = ocr_find_name_rect(doc, target_name, zoom=2.8)
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
            st.success("PDFs unidos correctamente.")

    if st.session_state.merged_pdf_bytes:
        st.divider()
        st.subheader("Descarga y firma opcional")

        merged_pdf_bytes = st.session_state.merged_pdf_bytes
        outname = output_name if output_name.lower().endswith(".pdf") else output_name + ".pdf"

        st.download_button(
            "⬇️ Descargar PDF unido",
            data=merged_pdf_bytes,
            file_name=outname,
            mime="application/pdf",
            key="dl_merged"
        )

        if not st.session_state.detected:
            st.info("No se detectó el nombre. No se habilita la firma.")
        else:
            st.success(
                f"Nombre detectado. Método: {st.session_state.det_method}. "
                f"Página: {st.session_state.det_page + 1}"
            )

            preview_zoom = st.slider("Zoom previsualización", 1.0, 3.5, 2.0, 0.1, key="preview_zoom")

            doc = fitz.open(stream=merged_pdf_bytes, filetype="pdf")
            page = doc[st.session_state.det_page]
            rect_pdf = fitz.Rect(*st.session_state.det_rect)

            img_page = render_page_image(page, zoom=preview_zoom)
            rect_img = rect_pdf_to_img(rect_pdf, zoom=preview_zoom)

            st.image(draw_highlight(img_page, rect_img), caption="Nombre detectado", use_container_width=True)

            wants_sign = st.toggle("¿Deseas firmar este documento?", value=False, key="wants_sign")

            if wants_sign:
                sig_file = st.file_uploader(
                    "Sube la firma (PNG/JPG)",
                    type=["png", "jpg", "jpeg"],
                    key="sig_uploader"
                )

                st.markdown("#### Ajustes de firma")
                gap = st.slider("Espacio entre firma y nombre", 0, 40, 10, key="gap")
                pad = st.slider("Margen", 0, 20, 6, key="pad")
                scale_w = st.slider("Escala ancho firma", 0.8, 2.5, 1.4, 0.1, key="scale_w")
                scale_h = st.slider("Escala alto firma", 0.8, 4.0, 2.0, 0.1, key="scale_h")

                st.markdown("#### Mover firma")
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

                st.caption(
                    f"Desplazamiento actual → dx: {st.session_state.sig_dx} | dy: {st.session_state.sig_dy}"
                )

                if sig_file:
                    sig_img = Image.open(sig_file).convert("RGBA")

                    preview_with_sig = draw_signature_preview_above(
                        img_page,
                        rect_pdf,
                        sig_img,
                        zoom=preview_zoom,
                        gap=gap,
                        pad=pad,
                        scale_w=scale_w,
                        scale_h=scale_h,
                        dx_pdf=st.session_state.sig_dx,
                        dy_pdf=st.session_state.sig_dy,
                    )

                    st.image(
                        preview_with_sig,
                        caption="Previsualización con firma",
                        use_container_width=True
                    )

                    if st.button("🔒 Confirmar y generar PDF firmado", key="confirm_sign"):
                        doc2 = fitz.open(stream=merged_pdf_bytes, filetype="pdf")
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
                            "⬇️ Descargar PDF firmado",
                            data=out,
                            file_name="PDF_unido_firmado.pdf",
                            mime="application/pdf",
                            key="dl_signed"
                        )

            doc.close()

    st.markdown("</div>", unsafe_allow_html=True)

# =========================================================
# TAB 2: IMÁGENES -> PDF
# =========================================================
with tab2:
    st.markdown('<div class="custom-box">', unsafe_allow_html=True)
    st.subheader("Convertir JPG/JPEG/PNG a PDF")

    col_a, col_b = st.columns([1, 1])
    with col_a:
        if st.button("🔄 Reiniciar sección imágenes"):
            reset_images_section()

    uploaded_images = st.file_uploader(
        "Sube una o varias imágenes",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
        key="images_uploader"
    )

    if uploaded_images:
        st.write("**Imágenes cargadas:**")
        for i, img in enumerate(uploaded_images, start=1):
            st.write(f"{i}. {img.name}")

        mode = st.radio(
            "¿Qué deseas hacer?",
            [
                "Convertir y descargar PDFs individuales",
                "Convertir y unificar en un solo PDF",
                "Hacer ambas opciones"
            ],
            key="images_mode"
        )

        if st.button("🖼️ Convertir imágenes", key="convert_images_btn"):
            with st.spinner("Convirtiendo imágenes a PDF..."):
                pdfs, pdf_names = convert_multiple_images_to_individual_pdfs(uploaded_images)

            st.session_state.converted_images_pdf_bytes = pdfs
            st.session_state.converted_images_names = pdf_names

            if mode in ["Convertir y unificar en un solo PDF", "Hacer ambas opciones"]:
                with st.spinner("Unificando PDFs generados desde imágenes..."):
                    st.session_state.merged_images_pdf_bytes = merge_image_pdfs(pdfs)
            else:
                st.session_state.merged_images_pdf_bytes = None

            st.success("Conversión completada.")

    if st.session_state.converted_images_pdf_bytes:
        st.divider()
        st.subheader("Descargas disponibles")

        mode = st.session_state.get("images_mode", "Convertir y descargar PDFs individuales")

        if mode in ["Convertir y descargar PDFs individuales", "Hacer ambas opciones"]:
            zip_bytes = build_zip_of_pdfs(
                st.session_state.converted_images_pdf_bytes,
                st.session_state.converted_images_names
            )

            st.download_button(
                "⬇️ Descargar ZIP con PDFs individuales",
                data=zip_bytes,
                file_name="imagenes_convertidas_pdf.zip",
                mime="application/zip",
                key="download_zip_individuals"
            )

            with st.expander("Ver descargas individuales una por una"):
                for pdf_bytes, pdf_name in zip(
                    st.session_state.converted_images_pdf_bytes,
                    st.session_state.converted_images_names
                ):
                    st.download_button(
                        f"Descargar {pdf_name}",
                        data=pdf_bytes,
                        file_name=pdf_name,
                        mime="application/pdf",
                        key=f"dl_{pdf_name}"
                    )

        if mode in ["Convertir y unificar en un solo PDF", "Hacer ambas opciones"]:
            if st.session_state.merged_images_pdf_bytes:
                st.download_button(
                    "⬇️ Descargar PDF unificado de imágenes",
                    data=st.session_state.merged_images_pdf_bytes,
                    file_name="imagenes_unificadas.pdf",
                    mime="application/pdf",
                    key="download_merged_images_pdf"
                )

    st.markdown("</div>", unsafe_allow_html=True)
