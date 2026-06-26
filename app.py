from flask import Flask, request, render_template, jsonify, send_file
import fitz
import io
import os
import zipfile
import base64
from PIL import Image, ImageEnhance, ImageDraw
from werkzeug.utils import secure_filename
from pdf2docx import Converter
from docx import Document

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 

# --- Routes for all Tools ---
@app.route('/', methods=['GET'])
def index(): return render_template('index.html')

@app.route('/print-studio', methods=['GET'])
def print_studio(): return render_template('print_studio.html')

@app.route('/compress_page', methods=['GET'])
def compress_page(): return render_template('compress.html')

@app.route('/image_pdf_page', methods=['GET'])
def image_pdf_page(): return render_template('image_pdf.html')

@app.route('/word_pdf_page', methods=['GET'])
def word_pdf_page(): return render_template('word_pdf.html')

@app.route('/merge_page', methods=['GET'])
def merge_page(): return render_template('merge.html')

@app.route('/split_page', methods=['GET'])
def split_page(): return render_template('split.html')

@app.route('/security_page', methods=['GET'])
def security_page(): return render_template('security.html')

@app.route('/image-crop', methods=['GET'])
def image_crop_page(): return render_template('image_crop.html')

# --- Backend APIs ---
@app.route('/compress_batch', methods=['POST'])
def compress_batch():
    try:
        files = request.files.getlist('files')
        compressed_files = []
        for file in files:
            doc = fitz.open(stream=file.read(), filetype="pdf")
            pdf_bytes = doc.tobytes(garbage=4, deflate=True)
            compressed_files.append((secure_filename(file.filename), pdf_bytes))
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zipf:
            for fname, fbytes in compressed_files:
                zipf.writestr("compressed_" + fname, fbytes)
        return jsonify({"success": True, "file_data": base64.b64encode(zip_buffer.getvalue()).decode('utf-8')})
    except Exception as e: return jsonify({"success": False, "error": str(e)})

@app.route('/images_to_pdf', methods=['POST'])
def images_to_pdf():
    try:
        files = request.files.getlist('files')
        new_doc = fitz.open()
        for file in files:
            img = Image.open(io.BytesIO(file.read())).convert("RGB")
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=90)
            img_doc = fitz.open("pdf", fitz.open("jpeg", img_byte_arr.getvalue()).convert_to_pdf())
            new_doc.insert_pdf(img_doc)
        return jsonify({"success": True, "file_data": base64.b64encode(new_doc.tobytes()).decode('utf-8')})
    except Exception as e: return jsonify({"success": False, "error": str(e)})

@app.route('/merge_pdfs', methods=['POST'])
def merge_pdfs():
    try:
        files = request.files.getlist('files')
        new_doc = fitz.open()
        for file in files: new_doc.insert_pdf(fitz.open(stream=file.read(), filetype="pdf"))
        return jsonify({"success": True, "file_data": base64.b64encode(new_doc.tobytes()).decode('utf-8')})
    except Exception as e: return jsonify({"success": False, "error": str(e)})

@app.route('/split_pdf', methods=['POST'])
def split_pdf():
    try:
        file = request.files['file']
        pages = request.form.get('pages', '1')
        doc = fitz.open(stream=file.read(), filetype="pdf")
        doc.select([int(p.strip()) - 1 for p in pages.split(',') if p.strip().isdigit()])
        return jsonify({"success": True, "file_data": base64.b64encode(doc.tobytes()).decode('utf-8')})
    except Exception as e: return jsonify({"success": False, "error": str(e)})

@app.route('/protect_pdf', methods=['POST'])
def protect_pdf():
    try:
        file = request.files['file']
        password = request.form.get('password', '')
        doc = fitz.open(stream=file.read(), filetype="pdf")
        return jsonify({"success": True, "file_data": base64.b64encode(doc.tobytes(user_pw=password, owner_pw=password)).decode('utf-8')})
    except Exception as e: return jsonify({"success": False, "error": str(e)})

@app.route('/process-image-crop', methods=['POST'])
def process_image_crop():
    try:
        file = request.files['file']
        img = Image.open(file)
        x, y = int(float(request.form.get('x', 0))), int(float(request.form.get('y', 0)))
        w, h = int(float(request.form.get('width', img.width))), int(float(request.form.get('height', img.height)))
        img = img.crop((x, y, x + w, y + h))
        img_byte = io.BytesIO()
        img.save(img_byte, format='JPEG', quality=95)
        img_byte.seek(0)
        return send_file(img_byte, mimetype='image/jpeg')
    except Exception as e: return jsonify({"success": False, "error": str(e)})

# --- Final Print Studio Engine ---
@app.route('/process-print-studio', methods=['POST'])
def process_print_studio():
    try:
        job_type = request.form.get('job_type', 'id_card')
        paper_size = request.form.get('paper_size', 'a4')
        lamination_mode = request.form.get('lamination_mode', 'false') == 'true'

        def apply_graphics(img):
            bright = float(request.form.get('brightness', 1.0))
            cont = float(request.form.get('contrast', 1.0))
            sharp = float(request.form.get('sharpness', 1.0))
            if bright != 1.0: img = ImageEnhance.Brightness(img).enhance(bright)
            if cont != 1.0: img = ImageEnhance.Contrast(img).enhance(cont)
            if sharp != 1.0: img = ImageEnhance.Sharpness(img).enhance(sharp)
            return img

        if job_type == 'passport':
            paper_dims = {'a4': (2480, 3508), '4x6': (1800, 1200), '5x7': (2100, 1500)}
        else:
            paper_dims = {'a4': (2480, 3508), '4x6': (1200, 1800), '5x7': (1500, 2100)}
            
        canvas_w, canvas_h = paper_dims.get(paper_size, (2480, 3508))
        canvas = Image.new("RGB", (canvas_w, canvas_h), "white")
        draw = ImageDraw.Draw(canvas)

        if job_type == 'id_card':
            id_w, id_h = (1050, 665) if paper_size in ['4x6', '5x7'] else (1200, 760)
            front = apply_graphics(Image.open(request.files['front_file']).convert("RGB")).resize((id_w, id_h), Image.Resampling.LANCZOS)
            back = apply_graphics(Image.open(request.files['back_file']).convert("RGB")).resize((id_w, id_h), Image.Resampling.LANCZOS)
            
            if lamination_mode:
                if back: back = back.rotate(180)
                mid_x = canvas_w // 2
                canvas.paste(front, (mid_x - id_w - 40, (canvas_h - id_h)//2))
                canvas.paste(back, (mid_x + 40, (canvas_h - id_h)//2))
                draw.line([(mid_x, 100), (mid_x, canvas_h - 100)], fill="#000000", width=8)
            else:
                fx = (canvas_w - id_w) // 2
                canvas.paste(front, (fx, 200))
                canvas.paste(back, (fx, 200 + id_h + 300))
                mid_y = 200 + id_h + 150
                for x_dash in range(fx - 50, fx + id_w + 50, 40):
                    draw.line([(x_dash, mid_y), (x_dash + 20, mid_y)], fill="#000000", width=8)
        
        else:
            photo = apply_graphics(Image.open(request.files['passport_file']).convert("RGB")).resize((380, 490), Image.Resampling.LANCZOS)
            total = int(request.form.get('photo_count', 8))
            margins = {'a4': (100, 100), '4x6': (80, 60), '5x7': (90, 80)}
            gap = {'a4': (50, 50), '4x6': (40, 40), '5x7': (45, 45)}
            mx, my = margins.get(paper_size, (50, 50))
            gx, gy = gap.get(paper_size, (30, 30))
            cols = 6 if paper_size == 'a4' else (5 if paper_size == '5x7' else 4)

            for i in range(total):
                x = mx + (i % cols) * (380 + gx)
                y = my + (i // cols) * (490 + gy)
                canvas.paste(photo, (x, y))

        img_byte = io.BytesIO()
        canvas.save(img_byte, format='JPEG', quality=100, dpi=(300, 300))
        img_byte.seek(0)
        return send_file(img_byte, mimetype='image/jpeg', as_attachment=True, download_name="Print_Sheet.jpg")
    except Exception as e: return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
