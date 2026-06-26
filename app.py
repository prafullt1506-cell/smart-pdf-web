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

@app.route('/', methods=['GET'])
def index(): return render_template('index.html')

@app.route('/print-studio', methods=['GET'])
def print_studio(): return render_template('print_studio.html')

# ==========================================
# 🛠️ PDF & IMAGE UTILITY ENGINES (जुनं जसं आहे तसं)
# ==========================================
@app.route('/compress_batch', methods=['POST'])
def compress_batch():
    try:
        files = request.files.getlist('files')
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
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

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
        out_bytes = new_doc.tobytes()
        return jsonify({"success": True, "file_data": base64.b64encode(out_bytes).decode('utf-8')})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/merge_pdfs', methods=['POST'])
def merge_pdfs():
    try:
        files = request.files.getlist('files')
        new_doc = fitz.open()
        for file in files:
            new_doc.insert_pdf(fitz.open(stream=file.read(), filetype="pdf"))
        out_bytes = new_doc.tobytes()
        return jsonify({"success": True, "file_data": base64.b64encode(out_bytes).decode('utf-8')})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/split_pdf', methods=['POST'])
def split_pdf():
    try:
        file = request.files['file']
        pages = request.form.get('pages', '1')
        doc = fitz.open(stream=file.read(), filetype="pdf")
        page_list = [int(p.strip()) - 1 for p in pages.split(',') if p.strip().isdigit()]
        doc.select(page_list)
        out_bytes = doc.tobytes()
        return jsonify({"success": True, "file_data": base64.b64encode(out_bytes).decode('utf-8')})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/protect_pdf', methods=['POST'])
def protect_pdf():
    try:
        file = request.files['file']
        password = request.form.get('password', '')
        doc = fitz.open(stream=file.read(), filetype="pdf")
        out_bytes = doc.tobytes(user_pw=password, owner_pw=password)
        return jsonify({"success": True, "file_data": base64.b64encode(out_bytes).decode('utf-8')})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

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
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# ==========================================
# 🖨️👑 ENGINE: PRO PRINT STUDIO (Updated Matrix & Fold Lines)
# ==========================================
@app.route('/process-print-studio', methods=['POST'])
def process_print_studio():
    try:
        job_type = request.form.get('job_type', 'id_card')
        paper_size = request.form.get('paper_size', 'a4')
        lamination_mode = request.form.get('lamination_mode', 'false') == 'true'

        bright = float(request.form.get('brightness', 1.0))
        cont = float(request.form.get('contrast', 1.0))
        sharp = float(request.form.get('sharpness', 1.0))

        def apply_graphics(img):
            if bright != 1.0: img = ImageEnhance.Brightness(img).enhance(bright)
            if cont != 1.0: img = ImageEnhance.Contrast(img).enhance(cont)
            if sharp != 1.0: img = ImageEnhance.Sharpness(img).enhance(sharp)
            return img

        # 🎯 4x6 Photo Studio साठी लँडस्केप आकार (१८००x१२००) जेणेकरून ८ फोटो परफेक्ट बसतील
        if job_type == 'passport' and paper_size == '4x6':
            canvas_w, canvas_h = 1800, 1200 
        else:
            paper_dims = {'a4': (2480, 3508), '4x6': (1200, 1800)}
            canvas_w, canvas_h = paper_dims.get(paper_size, (2480, 3508))

        canvas = Image.new("RGB", (canvas_w, canvas_h), "white")
        draw = ImageDraw.Draw(canvas)

        if job_type == 'id_card':
            id_w, id_h = (1050, 665) if paper_size == '4x6' else (1200, 760)

            front = Image.open(request.files['front_file']).convert("RGB")
            back = Image.open(request.files['back_file']).convert("RGB")
            front = apply_graphics(front).resize((id_w, id_h), Image.Resampling.LANCZOS)
            back = apply_graphics(back).resize((id_w, id_h), Image.Resampling.LANCZOS)
            
            ImageDraw.Draw(front).rectangle([(0,0), (id_w-1, id_h-1)], outline="#cbd5e1", width=3)
            ImageDraw.Draw(back).rectangle([(0,0), (id_w-1, id_h-1)], outline="#cbd5e1", width=3)

            if paper_size == '4x6':
                gap = 150
                fx = (canvas_w - id_w) // 2 
                fy = 100
                bx = fx
                by = fy + id_h + gap
                canvas.paste(front, (fx, fy))
                canvas.paste(back, (bx, by))
                
                # Dark Fold Line
                mid_y = fy + id_h + (gap // 2)
                for x_dash in range(fx, fx + id_w, 30):
                    draw.line([(x_dash, mid_y), (x_dash + 15, mid_y)], fill="#000000", width=5)

            else:
                if lamination_mode:
                    gap = 80
                    mid_x = canvas_w // 2
                    fx = mid_x - id_w - (gap // 2)
                    bx = mid_x + (gap // 2)
                    fy = 150
                    canvas.paste(front, (fx, fy))
                    canvas.paste(back, (bx, fy))
                    
                    # 🎯 Dark Lamination Fold Line (Vertical)
                    for y_dash in range(fy - 50, fy + id_h + 50, 30):
                        draw.line([(mid_x, y_dash), (mid_x, y_dash + 15)], fill="#000000", width=6)
                else:
                    gap = 350
                    fx = (canvas_w - id_w) // 2 
                    fy = 150
                    bx = fx  
                    by = fy + id_h + gap
                    canvas.paste(front, (fx, fy))
                    canvas.paste(back, (bx, by))
                    
                    # 🎯 Dark Fold Line (Horizontal)
                    mid_y = fy + id_h + (gap // 2)
                    for x_dash in range(fx - 50, fx + id_w + 50, 30):
                        draw.line([(x_dash, mid_y), (x_dash + 15, mid_y)], fill="#000000", width=6)

        else:
            # 🎯 PHOTO STUDIO (Exact Matrix)
            photo = Image.open(request.files['passport_file']).convert("RGB")
            photo = apply_graphics(photo)
            
            total_photos = int(request.form.get('photo_count', 8))
            photo_w, photo_h = 380, 490 # Standard studio crop size
            
            if paper_size == '4x6':
                cols, rows = 4, 2  # 8 Photos
                margin_x, margin_y = 120, 80
                gap_x, gap_y = 20, 40
            else:
                cols, rows = 6, 6  # 36 Photos
                margin_x, margin_y = 70, 100
                gap_x, gap_y = 15, 60

            photo = photo.resize((photo_w, photo_h), Image.Resampling.LANCZOS)
            ImageDraw.Draw(photo).rectangle([(0,0), (photo_w-1, photo_h-1)], outline="#cbd5e1", width=3)
            
            photo_count = 0
            for r in range(rows):
                for c in range(cols):
                    if photo_count >= total_photos: break
                    x = margin_x + c * (photo_w + gap_x)
                    y = margin_y + r * (photo_h + gap_y)
                    canvas.paste(photo, (x, y))
                    photo_count += 1

        img_byte = io.BytesIO()
        canvas.save(img_byte, format='JPEG', quality=100, dpi=(300, 300))
        img_byte.seek(0)
        return send_file(img_byte, mimetype='image/jpeg', as_attachment=True, download_name="Print_Sheet.jpg")
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
