from flask import Flask, request, render_template, jsonify, send_file
import fitz
import io
import os
import zipfile
import base64
import tempfile
from PIL import Image, ImageEnhance
from werkzeug.utils import secure_filename
from pdf2docx import Converter
from docx import Document

app = Flask(__name__)

# 🛡️ ANTI-HANG SECURITY: ५० MB ची फाईल साईझ लिमिट
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 

# ==========================================
# 🌐 FRONTEND PAGE ROUTES (मेनू आणि पेजेस)
# ==========================================
@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/compress_page', methods=['GET'])
def compress_page():
    return render_template('compress.html')

@app.route('/image_pdf_page', methods=['GET'])
def image_pdf_page():
    return render_template('image_pdf.html')

@app.route('/word_pdf_page', methods=['GET'])
def word_pdf_page():
    return render_template('word_pdf.html')

@app.route('/merge_page', methods=['GET'])
def merge_page():
    return render_template('merge.html')

@app.route('/split_page', methods=['GET'])
def split_page():
    return render_template('split.html')

@app.route('/security_page', methods=['GET'])
def security_page():
    return render_template('protect.html')

@app.route('/image-crop', methods=['GET'])
def image_crop():
    return render_template('image_crop.html')

# ==========================================
# 🗜️ ENGINE 1: PDF COMPRESSOR
# ==========================================
@app.route('/compress_batch', methods=['POST'])
def compress_batch():
    if 'files' not in request.files:
        return jsonify({"error": "No files uploaded"}), 400
    files = request.files.getlist('files')
    if not files or files[0].filename == '':
        return jsonify({"error": "No files selected"}), 400

    target_kb = int(request.form.get('target_kb', 500))
    total_original_size = 0
    total_new_size = 0
    compressed_files = []

    for file in files:
        filename = secure_filename(file.filename)
        original_bytes = file.read()
        total_original_size += len(original_bytes) / 1024

        doc = fitz.open(stream=original_bytes, filetype="pdf")
        pdf_bytes = doc.tobytes(garbage=4, deflate=True, clean=True)

        if len(pdf_bytes) / 1024 > target_kb:
            settings = [(1.2, 55), (1.0, 45), (0.8, 35), (0.7, 25), (0.6, 15)]
            for zoom, quality in settings:
                new_doc = fitz.open()
                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                    img_byte_arr = io.BytesIO()
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    img.save(img_byte_arr, format='JPEG', optimize=True, quality=quality)
                    img_pdf_bytes = fitz.open("jpeg", img_byte_arr.getvalue()).convert_to_pdf()
                    new_doc.insert_pdf(fitz.open("pdf", img_pdf_bytes))

                pdf_bytes = new_doc.tobytes(garbage=4, deflate=True)
                new_doc.close()
                if len(pdf_bytes) / 1024 <= target_kb:
                    break
        doc.close()

        target_size_bytes = int(target_kb * 1024)
        if len(pdf_bytes) < target_size_bytes:
            padding_needed = target_size_bytes - len(pdf_bytes)
            pdf_bytes += b'\0' * padding_needed

        total_new_size += len(pdf_bytes) / 1024
        compressed_files.append((filename, pdf_bytes))

    if len(compressed_files) == 1:
        out_filename = "compressed_" + compressed_files[0][0]
        final_bytes = compressed_files[0][1]
        mime_type = "application/pdf"
    else:
        out_filename = "compressed_batch.zip"
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zipf:
            for fname, fbytes in compressed_files:
                zipf.writestr("compressed_" + fname, fbytes)
        final_bytes = zip_buffer.getvalue()
        mime_type = "application/zip"

    b64_data = base64.b64encode(final_bytes).decode('utf-8')
    return jsonify({
        "success": True,
        "original_kb": round(total_original_size, 1),
        "new_kb": round(total_new_size, 1),
        "file_name": out_filename,
        "mime_type": mime_type,
        "file_data": b64_data
    })

# ==========================================
# 🖼️ ENGINE 2: IMAGES TO PDF
# ==========================================
@app.route('/images_to_pdf', methods=['POST'])
def images_to_pdf():
    if 'files' not in request.files:
        return jsonify({"error": "No files uploaded"}), 400
    files = request.files.getlist('files')
    target_kb = int(request.form.get('target_kb', 500))
    
    total_image_size = 0
    new_doc = fitz.open()
    
    for file in files:
        img_bytes = file.read()
        total_image_size += len(img_bytes) / 1024
        try:
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=100)
            img_pdf_bytes = fitz.open("jpeg", img_byte_arr.getvalue()).convert_to_pdf()
            new_doc.insert_pdf(fitz.open("pdf", img_pdf_bytes))
        except:
            continue

    original_pdf_bytes = new_doc.tobytes(garbage=4, deflate=True)
    generated_pdf_kb = len(original_pdf_bytes) / 1024
    pdf_bytes = original_pdf_bytes 
    
    if len(pdf_bytes) / 1024 > target_kb:
        settings = [(1.0, 90), (0.9, 85), (0.8, 80)]
        for zoom, quality in settings:
            comp_doc = fitz.open()
            for page_num in range(len(new_doc)):
                page = new_doc.load_page(page_num)
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                img_byte_arr = io.BytesIO()
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                img.save(img_byte_arr, format='JPEG', optimize=True, quality=quality)
                img_pdf_bytes = fitz.open("jpeg", img_byte_arr.getvalue()).convert_to_pdf()
                comp_doc.insert_pdf(fitz.open("pdf", img_pdf_bytes))
            pdf_bytes = comp_doc.tobytes(garbage=4, deflate=True)
            comp_doc.close()
            if len(pdf_bytes) / 1024 <= target_kb:
                break
    new_doc.close()

    target_size_bytes = int(target_kb * 1024)
    if len(pdf_bytes) < target_size_bytes:
        pdf_bytes += b'\0' * (target_size_bytes - len(pdf_bytes))

    return jsonify({
        "success": True,
        "is_dual": True,
        "original_kb": round(total_image_size, 1),
        "generated_pdf_kb": round(generated_pdf_kb, 1),
        "new_kb": round(len(pdf_bytes) / 1024, 1),
        "file_name_orig": "Original_Images.pdf",
        "file_name_comp": "Target_Images.pdf",
        "mime_type": "application/pdf",
        "file_data_orig": base64.b64encode(original_pdf_bytes).decode('utf-8'),
        "file_data_comp": base64.b64encode(pdf_bytes).decode('utf-8')
    })

# ==========================================
# 📄 ENGINE 3: PDF TO IMAGES (ZIP)
# ==========================================
@app.route('/pdf_to_images', methods=['POST'])
def pdf_to_images():
    if 'files' not in request.files:
        return jsonify({"error": "No files uploaded"}), 400
    files = request.files.getlist('files')
    file = files[0]
    pdf_bytes = file.read()
    total_original_kb = len(pdf_bytes) / 1024
    
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zipf:
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
            img_byte_arr = io.BytesIO()
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            img.save(img_byte_arr, format='JPEG', quality=95)
            zipf.writestr(f"Page_{page_num + 1}.jpg", img_byte_arr.getvalue())
    doc.close()
    
    return jsonify({
        "success": True,
        "is_dual": False,
        "original_kb": round(total_original_kb, 1),
        "new_kb": round(len(zip_buffer.getvalue()) / 1024, 1),
        "file_name": "PDF_Pages_Images.zip",
        "mime_type": "application/zip",
        "file_data": base64.b64encode(zip_buffer.getvalue()).decode('utf-8')
    })

# ==========================================
# 📝 ENGINE 4: PDF TO WORD (.docx)
# ==========================================
@app.route('/pdf_to_word', methods=['POST'])
def pdf_to_word():
    file = request.files['files']
    original_kb = len(file.read()) / 1024
    file.seek(0)
    
    temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    temp_docx = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
    
    try:
        file.save(temp_pdf.name)
        cv = Converter(temp_pdf.name)
        cv.convert(temp_docx.name, start=0, end=None)
        cv.close()
        with open(temp_docx.name, 'rb') as f:
            docx_bytes = f.read()
        b64_data = base64.b64encode(docx_bytes).decode('utf-8')
    finally:
        if os.path.exists(temp_pdf.name): os.remove(temp_pdf.name)
        if os.path.exists(temp_docx.name): os.remove(temp_docx.name)

    return jsonify({
        "success": True,
        "original_kb": round(original_kb, 1),
        "new_kb": round(len(docx_bytes) / 1024, 1),
        "file_name": "Converted.docx",
        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "file_data": b64_data
    })

# ==========================================
# 📑 ENGINE 5: WORD TO PDF
# ==========================================
@app.route('/word_to_pdf', methods=['POST'])
def word_to_pdf():
    file = request.files['files']
    original_kb = len(file.read()) / 1024
    file.seek(0)
    
    try:
        doc = Document(file)
        pdf_doc = fitz.open()
        page = pdf_doc.new_page()
        y_position = 50
        for para in doc.paragraphs:
            if para.text.strip():
                if y_position > 780:
                    page = pdf_doc.new_page()
                    y_position = 50
                page.insert_text((50, y_position), para.text, fontname="helv", fontsize=11, color=(0, 0, 0))
                y_position += 20 
        pdf_bytes = pdf_doc.tobytes(deflate=True)
        pdf_doc.close()
        return jsonify({
            "success": True,
            "original_kb": round(original_kb, 1),
            "new_kb": round(len(pdf_bytes) / 1024, 1),
            "file_name": "Converted.pdf",
            "mime_type": "application/pdf",
            "file_data": base64.b64encode(pdf_bytes).decode('utf-8')
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==========================================
# 📂 ENGINE 6: MERGE MULTIPLE PDFs
# ==========================================
@app.route('/merge_pdfs', methods=['POST'])
def merge_pdfs():
    files = request.files.getlist('files')
    new_doc = fitz.open()
    total_input_kb = 0

    for file in files:
        pdf_bytes = file.read()
        total_input_kb += len(pdf_bytes) / 1024
        try:
            src_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            new_doc.insert_pdf(src_doc)
            src_doc.close()
        except Exception as e:
            return jsonify({"error": f"Error: {str(e)}"}), 400

    out_bytes = new_doc.tobytes(garbage=4, deflate=True)
    new_doc.close()

    return jsonify({
        "success": True,
        "original_kb": round(total_input_kb, 1),
        "new_kb": round(len(out_bytes) / 1024, 1),
        "file_name": "Merged_Document.pdf",
        "mime_type": "application/pdf",
        "file_data": base64.b64encode(out_bytes).decode('utf-8')
    })

# ==========================================
# ✂️ ENGINE 7: SPLIT PDF
# ==========================================
@app.route('/split_pdf', methods=['POST'])
def split_pdf():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files['file']
    pages_str = request.form.get('pages', '')
    try:
        pdf_bytes = file.read()
        original_kb = len(pdf_bytes) / 1024
        pages_to_keep = set()
        parts = pages_str.replace(" ", "").split(",")
        for part in parts:
            if "-" in part:
                start, end = part.split("-")
                for p in range(int(start), int(end) + 1):
                    pages_to_keep.add(p - 1)
            else:
                if part.isdigit():
                    pages_to_keep.add(int(part) - 1)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        valid_pages = [p for p in sorted(list(pages_to_keep)) if 0 <= p <= len(doc)-1]
        if not valid_pages:
            return jsonify({"error": "Selected pages do not exist"}), 400
        doc.select(valid_pages)
        out_bytes = doc.tobytes(garbage=4, deflate=True)
        doc.close()
        return jsonify({
            "success": True,
            "original_kb": round(original_kb, 1),
            "new_kb": round(len(out_bytes) / 1024, 1),
            "file_name": "Split_" + secure_filename(file.filename),
            "mime_type": "application/pdf",
            "file_data": base64.b64encode(out_bytes).decode('utf-8')
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==========================================
# 🔐 ENGINE 8: PROTECT & UNLOCK PDF
# ==========================================
@app.route('/protect_pdf', methods=['POST'])
def protect_pdf():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files['file']
    password = request.form.get('password', '')
    mode = request.form.get('mode', 'protect')
    
    if not password:
        return jsonify({"error": "Password is required"}), 400
        
    try:
        pdf_bytes = file.read()
        original_kb = len(pdf_bytes) / 1024
        
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        if mode == 'protect':
            doc.saveIncr() 
            out_bytes = doc.tobytes(
                garbage=4, 
                deflate=True, 
                user_pw=password, 
                owner_pw=password, 
                permissions=fitz.PDF_PERM_ACCESSIBILITY
            )
            out_filename = "Protected_" + secure_filename(file.filename)
        else:
            if doc.is_encrypted:
                auth_success = doc.authenticate(password)
                if not auth_success:
                    return jsonify({"error": "Incorrect password! Could not unlock PDF."}), 400
                out_bytes = doc.tobytes(garbage=4, deflate=True)
                out_filename = "Unlocked_" + secure_filename(file.filename)
            else:
                return jsonify({"error": "This PDF is already unlocked!"}), 400
                
        doc.close()
        return jsonify({
            "success": True,
            "original_kb": round(original_kb, 1),
            "new_kb": round(len(out_bytes) / 1024, 1),
            "file_name": out_filename,
            "mime_type": "application/pdf",
            "file_data": base64.b64encode(out_bytes).decode('utf-8')
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==========================================
# ✂️🖼️ ENGINE 9: PRO IMAGE CROPPER & ENHANCER (CM + Pixel + Custom DPI Target Array)
# ==========================================
@app.route('/process-image-crop', methods=['POST'])
def process_image_crop():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
            
        file = request.files['file']
        img = Image.open(file)
        
        original_format = img.format if img.format else 'JPEG'
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            original_format = 'JPEG'

        # 1. Cropping Engine Execution
        x = int(float(request.form.get('x', 0)))
        y = int(float(request.form.get('y', 0)))
        w = int(float(request.form.get('width', img.width)))
        h = int(float(request.form.get('height', img.height)))
        
        if w > 0 and h > 0:
            img = img.crop((x, y, x + w, y + h))

        # 2. Magic Enhance Matrix (Auto Clean & Sharp Filter)
        if request.form.get('enhance') == 'true':
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(1.6) 
            enhancer_contrast = ImageEnhance.Contrast(img)
            img = enhancer_contrast.enhance(1.15)
            enhancer_color = ImageEnhance.Color(img)
            img = enhancer_color.enhance(1.1)

        # 3. Dynamic Unit Resolution Target Parser (PX vs CM conversion with DPI)
        unit = request.form.get('unit', 'px')
        raw_w = request.form.get('target_w', '')
        raw_h = request.form.get('target_h', '')
        raw_dpi = request.form.get('target_dpi', '')

        # जर युजरने DPI दिला नसेल तर Default 300 DPI सेट करणे
        try:
            target_dpi = int(raw_dpi) if raw_dpi else 300
        except ValueError:
            target_dpi = 300

        target_w, target_h = None, None

        if raw_w and raw_h:
            try:
                if unit == 'cm':
                    # CM to Pixel Formula based on Custom DPI: Pixels = (CM / 2.54) * DPI
                    target_w = int((float(raw_w) / 2.54) * target_dpi)
                    target_h = int((float(raw_h) / 2.54) * target_dpi)
                else:
                    target_w = int(float(raw_w))
                    target_h = int(float(raw_h))
            except ValueError:
                pass

        # Perform High-Quality LANCZOS Resampling Matrix
        if target_w and target_h and target_w > 0 and target_h > 0:
            img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

        # 4. Byte Clamping Compression (KB Engine Clamping + DPI Binding)
        target_kb = request.form.get('target_kb')
        img_byte_arr = io.BytesIO()
        
        if target_kb and target_kb.isdigit():
            target_bytes = int(target_kb) * 1024
            quality = 95
            while quality > 15:
                img_byte_arr.seek(0)
                img_byte_arr.truncate()
                # DPI मेटाडेटा इमेजमध्ये सेव्ह करणे
                img.save(img_byte_arr, format=original_format, quality=quality, optimize=True, dpi=(target_dpi, target_dpi))
                if img_byte_arr.tell() <= target_bytes:
                    break
                quality -= 5
        else:
            # जर KB सेट केलं नसेल तर Best Quality सोबत DPI सेव्ह करणे
            img.save(img_byte_arr, format=original_format, quality=95, optimize=True, dpi=(target_dpi, target_dpi))

        img_byte_arr.seek(0)
        return send_file(img_byte_arr, mimetype=f'image/{original_format.lower()}', as_attachment=True, download_name=f"Pro_Studio_Render.{original_format.lower()}")

    except Exception as e:
        print("Error System Core Grid Failure:", e)
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
