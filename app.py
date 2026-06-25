from flask import Flask, request, render_template, jsonify, send_file
import fitz
import io
import os
import zipfile
import base64
import tempfile
from PIL import Image, ImageEnhance, ImageDraw
from werkzeug.utils import secure_filename
from pdf2docx import Converter
from docx import Document

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 

# ==========================================
# 🌐 FRONTEND PAGE ROUTES
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

@app.route('/print-studio', methods=['GET'])
def print_studio():
    return render_template('print_studio.html')

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
    return jsonify({"success": True, "original_kb": round(total_original_size, 1), "new_kb": round(total_new_size, 1), "file_name": out_filename, "mime_type": mime_type, "file_data": b64_data})

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
    return jsonify({"success": True, "is_dual": True, "original_kb": round(total_image_size, 1), "generated_pdf_kb": round(generated_pdf_kb, 1), "new_kb": round(len(pdf_bytes) / 1024, 1), "file_name_orig": "Original_Images.pdf", "file_name_comp": "Target_Images.pdf", "mime_type": "application/pdf", "file_data_orig": base64.b64encode(original_pdf_bytes).decode('utf-8'), "file_data_comp": base64.b64encode(pdf_bytes).decode('utf-8')})

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
    return jsonify({"success": True, "is_dual": False, "original_kb": round(total_original_kb, 1), "new_kb": round(len(zip_buffer.getvalue()) / 1024, 1), "file_name": "PDF_Pages_Images.zip", "mime_type": "application/zip", "file_data": base64.b64encode(zip_buffer.getvalue()).decode('utf-8')})

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
    return jsonify({"success": True, "original_kb": round(original_kb, 1), "new_kb": round(len(docx_bytes) / 1024, 1), "file_name": "Converted.docx", "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "file_data": b64_data})

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
        return jsonify({"success": True, "original_kb": round(original_kb, 1), "new_kb": round(len(pdf_bytes) / 1024, 1), "file_name": "Converted.pdf", "mime_type": "application/pdf", "file_data": base64.b64encode(pdf_bytes).decode('utf-8')})
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
    return jsonify({"success": True, "original_kb": round(total_input_kb, 1), "new_kb": round(len(out_bytes) / 1024, 1), "file_name": "Merged_Document.pdf", "mime_type": "application/pdf", "file_data": base64.b64encode(out_bytes).decode('utf-8')})

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
        return jsonify({"success": True, "original_kb": round(original_kb, 1), "new_kb": round(len(out_bytes) / 1024, 1), "file_name": "Split_" + secure_filename(file.filename), "mime_type": "application/pdf", "file_data": base64.b64encode(out_bytes).decode('utf-8')})
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
            out_bytes = doc.tobytes(garbage=4, deflate=True, user_pw=password, owner_pw=password, permissions=fitz.PDF_PERM_ACCESSIBILITY)
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
        return jsonify({"success": True, "original_kb": round(original_kb, 1), "new_kb": round(len(out_bytes) / 1024, 1), "file_name": out_filename, "mime_type": "application/pdf", "file_data": base64.b64encode(out_bytes).decode('utf-8')})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==========================================
# ✂️🖼️ ENGINE 9: PRO IMAGE CROPPER & ENHANCER
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
        x = int(float(request.form.get('x', 0)))
        y = int(float(request.form.get('y', 0)))
        w = int(float(request.form.get('width', img.width)))
        h = int(float(request.form.get('height', img.height)))
        if w > 0 and h > 0:
            img = img.crop((x, y, x + w, y + h))
        if request.form.get('enhance') == 'true':
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(1.6) 
            enhancer_contrast = ImageEnhance.Contrast(img)
            img = enhancer_contrast.enhance(1.15)
            enhancer_color = ImageEnhance.Color(img)
            img = enhancer_color.enhance(1.1)
        unit = request.form.get('unit', 'px')
        raw_w = request.form.get('target_w', '')
        raw_h = request.form.get('target_h', '')
        raw_dpi = request.form.get('target_dpi', '')
        try: target_dpi = int(raw_dpi) if raw_dpi else 300
        except ValueError: target_dpi = 300
        target_w, target_h = None, None
        if raw_w and raw_h:
            try:
                if unit == 'cm':
                    target_w = int((float(raw_w) / 2.54) * target_dpi)
                    target_h = int((float(raw_h) / 2.54) * target_dpi)
                else:
                    target_w = int(float(raw_w))
                    target_h = int(float(raw_h))
            except ValueError: pass
        if target_w and target_h and target_w > 0 and target_h > 0:
            img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        target_kb = request.form.get('target_kb')
        img_byte_arr = io.BytesIO()
        if target_kb and target_kb.isdigit():
            target_bytes = int(target_kb) * 1024
            quality = 95
            while quality > 15:
                img_byte_arr.seek(0)
                img_byte_arr.truncate()
                img.save(img_byte_arr, format=original_format, quality=quality, optimize=True, dpi=(target_dpi, target_dpi))
                if img_byte_arr.tell() <= target_bytes: break
                quality -= 5
        else:
            img.save(img_byte_arr, format=original_format, quality=95, optimize=True, dpi=(target_dpi, target_dpi))
        img_byte_arr.seek(0)
        return send_file(img_byte_arr, mimetype=f'image/{original_format.lower()}', as_attachment=True, download_name=f"Edited_Image.{original_format.lower()}")
    except Exception as e:
        print("Error:", e)
        return jsonify({'error': str(e)}), 500

# ==========================================
# 🖨️👑 ENGINE 10: PRO PRINT STUDIO (Ultimate Layout Logic)
# ==========================================
@app.route('/process-print-studio', methods=['POST'])
def process_print_studio():
    try:
        job_type = request.form.get('job_type', 'id_card')
        paper_size = request.form.get('paper_size', 'a4')
        lamination_mode = request.form.get('lamination_mode', 'false') == 'true'

        paper_dims = {
            'a4': (2480, 3508), 'letter': (2550, 3300), 'legal': (2550, 4200),
            '4x6': (1200, 1800), '5x7': (1500, 2100), '8x10': (2400, 3000)
        }
        canvas_w, canvas_h = paper_dims.get(paper_size, (2480, 3508))

        canvas = Image.new("RGB", (canvas_w, canvas_h), "white")
        draw = ImageDraw.Draw(canvas)

        # 🟢 NARROW MARGINS (For maximum paper saving)
        margin_x = 60 
        margin_y = 60 

        if job_type == 'id_card':
            # 🟢 ID CARD SIZE INCREASED (+5% approx for better A4 visibility)
            id_w, id_h = 1040, 660  
            
            front = Image.open(request.files['front_file']).convert("RGB")
            back = Image.open(request.files['back_file']).convert("RGB")
            front = front.resize((id_w, id_h), Image.Resampling.LANCZOS)
            back = back.resize((id_w, id_h), Image.Resampling.LANCZOS)

            ImageDraw.Draw(front).rectangle([(0,0), (id_w-1, id_h-1)], outline="#cbd5e1", width=2)
            ImageDraw.Draw(back).rectangle([(0,0), (id_w-1, id_h-1)], outline="#cbd5e1", width=2)

            if paper_size in ['4x6', '5x7', '8x10']:
                # Vertical Small Papers: Top-Left, One below another
                fx, fy = margin_x, margin_y
                bx, by = margin_x, fy + id_h + 50 

                if lamination_mode:
                    back = back.rotate(180)
                    mid_y = fy + id_h + 25
                    for x_dash in range(margin_x, margin_x + id_w, 20):
                        draw.line([(x_dash, mid_y), (x_dash + 10, mid_y)], fill="#94a3b8", width=3)

                canvas.paste(front, (fx, fy))
                canvas.paste(back, (bx, by))
            else:
                # Wide Sheets (A4, Letter, Legal)
                if lamination_mode:
                    # 🟢 LAMINATION ON: Top-Center, Side-by-Side!
                    gap = 80
                    total_width = (id_w * 2) + gap
                    start_x = (canvas_w - total_width) // 2  # Center horizontally
                    
                    fx, fy = start_x, margin_y
                    bx, by = start_x + id_w + gap, margin_y 

                    mid_x = start_x + id_w + (gap // 2)
                    for y_dash in range(margin_y, margin_y + id_h, 20):
                        draw.line([(mid_x, y_dash), (mid_x, y_dash + 10)], fill="#94a3b8", width=3)
                else:
                    # 🟢 LAMINATION OFF (Normal): Top-Center, One Below Another!
                    gap = 80
                    fx = (canvas_w - id_w) // 2
                    fy = margin_y
                    bx = fx
                    by = fy + id_h + gap

                canvas.paste(front, (fx, fy))
                canvas.paste(back, (bx, by))

        else:
            # PHOTO MAKER LOGIC
            photo_size_key = request.form.get('photo_size', 'passport')
            total_photos = int(request.form.get('photo_count', 8))
            
            sizes_map = {
                'stamp': (236, 295), 'passport': (413, 531), 'visa': (590, 590)
            }
            pass_w, pass_h = sizes_map.get(photo_size_key, (413, 531))
            photo = Image.open(request.files['passport_file']).convert("RGB")
            photo = photo.resize((pass_w, pass_h), Image.Resampling.LANCZOS)
            ImageDraw.Draw(photo).rectangle([(0,0), (pass_w-1, pass_h-1)], outline="#cbd5e1", width=2)

            gap_x, gap_y = 40, 50
            
            # Start from Top-Left corner strictly!
            start_x = margin_x
            start_y = margin_y
            
            cols_per_row = max(1, (canvas_w - (margin_x * 2)) // (pass_w + gap_x))

            for index in range(total_photos):
                row = index // cols_per_row
                col = index % cols_per_row
                
                x = start_x + col * (pass_w + gap_x)
                y = start_y + row * (pass_h + gap_y)

                if y + pass_h > canvas_h - margin_y:
                    break 

                canvas.paste(photo, (x, y))

        img_byte_arr = io.BytesIO()
        canvas.save(img_byte_arr, format='JPEG', quality=98, dpi=(300, 300))
        img_byte_arr.seek(0)

        return send_file(img_byte_arr, mimetype='image/jpeg', as_attachment=True, download_name=f"Print_Ready_Sheet.jpg")

    except Exception as e:
        print("Print Studio System Error:", e)
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
