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
# 🌐 FRONTEND ROUTES
# ==========================================
@app.route('/', methods=['GET'])
def index(): return render_template('index.html')

@app.route('/print-studio', methods=['GET'])
def print_studio(): return render_template('print_studio.html')

# ==========================================
# 🛠️ PDF & IMAGE UTILITY ENGINES
# ==========================================

@app.route('/compress_batch', methods=['POST'])
def compress_batch():
    files = request.files.getlist('files')
    target_kb = int(request.form.get('target_kb', 500))
    compressed_files = []
    for file in files:
        filename = secure_filename(file.filename)
        doc = fitz.open(stream=file.read(), filetype="pdf")
        pdf_bytes = doc.tobytes(garbage=4, deflate=True)
        compressed_files.append((filename, pdf_bytes))
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zipf:
        for fname, fbytes in compressed_files:
            zipf.writestr("compressed_" + fname, fbytes)
    return jsonify({"success": True, "file_data": base64.b64encode(zip_buffer.getvalue()).decode('utf-8')})

@app.route('/images_to_pdf', methods=['POST'])
def images_to_pdf():
    files = request.files.getlist('files')
    new_doc = fitz.open()
    for file in files:
        img = Image.open(io.BytesIO(file.read())).convert("RGB")
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG', quality=90)
        new_doc.insert_pdf(fitz.open("pdf", img_byte_arr.getvalue()))
    out_bytes = new_doc.tobytes()
    return jsonify({"success": True, "file_data": base64.b64encode(out_bytes).decode('utf-8')})

@app.route('/merge_pdfs', methods=['POST'])
def merge_pdfs():
    files = request.files.getlist('files')
    new_doc = fitz.open()
    for file in files:
        new_doc.insert_pdf(fitz.open(stream=file.read(), filetype="pdf"))
    out_bytes = new_doc.tobytes()
    return jsonify({"success": True, "file_data": base64.b64encode(out_bytes).decode('utf-8')})

@app.route('/split_pdf', methods=['POST'])
def split_pdf():
    file = request.files['file']
    pages = request.form.get('pages', '1')
    doc = fitz.open(stream=file.read(), filetype="pdf")
    doc.select([int(pages)-1])
    out_bytes = doc.tobytes()
    return jsonify({"success": True, "file_data": base64.b64encode(out_bytes).decode('utf-8')})

@app.route('/protect_pdf', methods=['POST'])
def protect_pdf():
    file = request.files['file']
    password = request.form.get('password', '')
    doc = fitz.open(stream=file.read(), filetype="pdf")
    out_bytes = doc.tobytes(user_pw=password, owner_pw=password)
    return jsonify({"success": True, "file_data": base64.b64encode(out_bytes).decode('utf-8')})

@app.route('/process-image-crop', methods=['POST'])
def process_image_crop():
    file = request.files['file']
    img = Image.open(file)
    x, y = int(float(request.form.get('x', 0))), int(float(request.form.get('y', 0)))
    w, h = int(float(request.form.get('width', img.width))), int(float(request.form.get('height', img.height)))
    img = img.crop((x, y, x + w, y + h))
    img_byte = io.BytesIO()
    img.save(img_byte, format='JPEG', quality=95)
    img_byte.seek(0)
    return send_file(img_byte, mimetype='image/jpeg')

@app.route('/word_to_pdf', methods=['POST'])
def word_to_pdf():
    file = request.files['files']
    doc = Document(file)
    pdf_doc = fitz.open()
    # (Word conversion logic...)
    return jsonify({"success": True})

@app.route('/pdf_to_word', methods=['POST'])
def pdf_to_word():
    file = request.files['files']
    # (PDF conversion logic...)
    return jsonify({"success": True})

# ==========================================
# 🖨️👑 ENGINE: PRO PRINT STUDIO (Perfect Layouts)
# ==========================================
@app.route('/process-print-studio', methods=['POST'])
def process_print_studio():
    try:
        job_type = request.form.get('job_type', 'id_card')
        paper_size = request.form.get('paper_size', 'a4')
        lamination_mode = request.form.get('lamination_mode', 'false') == 'true'

        paper_dims = {
            'a4': (2480, 3508), '4x6': (1200, 1800), '5x7': (1500, 2100)
        }
        canvas_w, canvas_h = paper_dims.get(paper_size, (2480, 3508))
        canvas = Image.new("RGB", (canvas_w, canvas_h), "white")
        draw = ImageDraw.Draw(canvas)
        margin_x, margin_y = 60, 60 

        if job_type == 'id_card':
            id_w, id_h = 1200, 760  # Bold Size
            front = Image.open(request.files['front_file']).convert("RGB").resize((id_w, id_h), Image.Resampling.LANCZOS)
            back = Image.open(request.files['back_file']).convert("RGB").resize((id_w, id_h), Image.Resampling.LANCZOS)
            
            ImageDraw.Draw(front).rectangle([(0,0), (id_w-1, id_h-1)], outline="#cbd5e1", width=2)
            ImageDraw.Draw(back).rectangle([(0,0), (id_w-1, id_h-1)], outline="#cbd5e1", width=2)

            if paper_size in ['4x6', '5x7']:
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
                if lamination_mode:
                    gap = 80
                    mid_x = canvas_w // 2
                    fx = mid_x - id_w - (gap // 2)
                    bx = mid_x + (gap // 2)
                    fy, by = margin_y, margin_y 
                    for y_dash in range(margin_y, margin_y + id_h, 20):
                        draw.line([(mid_x, y_dash), (mid_x, y_dash + 10)], fill="#94a3b8", width=3)
                    canvas.paste(front, (fx, fy))
                    canvas.paste(back, (bx, by))
                else:
                    # 🎯 NORMAL MODE: TOP-CENTER, ONE BELOW ANOTHER
                    gap = 120 
                    fx = (canvas_w - id_w) // 2 
                    fy = margin_y
                    bx = fx  
                    by = fy + id_h + gap
                    canvas.paste(front, (fx, fy))
                    canvas.paste(back, (bx, by))
        else:
            # 🎯 PHOTO STUDIO: Row Flow
            photo_size_key = request.form.get('photo_size', 'passport')
            total_photos = int(request.form.get('photo_count', 8))
            sizes_map = { 'stamp': (236, 295), 'passport': (413, 531) }
            pass_w, pass_h = sizes_map.get(photo_size_key, (413, 531))
            photo = Image.open(request.files['passport_file']).convert("RGB").resize((pass_w, pass_h), Image.Resampling.LANCZOS)
            ImageDraw.Draw(photo).rectangle([(0,0), (pass_w-1, pass_h-1)], outline="#cbd5e1", width=2)
            
            gap_x, gap_y = 30, 40
            cols_per_row = max(1, (canvas_w - (margin_x * 2)) // (pass_w + gap_x))
            for index in range(total_photos):
                row = index // cols_per_row
                col = index % cols_per_row
                x = margin_x + col * (pass_w + gap_x)
                y = margin_y + row * (pass_h + gap_y)
                if y + pass_h > canvas_h - margin_y: break 
                canvas.paste(photo, (x, y))

        img_byte = io.BytesIO()
        canvas.save(img_byte, format='JPEG', quality=100, dpi=(300, 300))
        img_byte.seek(0)
        return send_file(img_byte, mimetype='image/jpeg', as_attachment=True, download_name="Print_Sheet.jpg")
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
