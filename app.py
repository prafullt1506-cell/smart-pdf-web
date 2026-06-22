from flask import Flask, request, render_template, jsonify
import fitz
import io
from PIL import Image
from werkzeug.utils import secure_filename
import zipfile
import base64
import os

app = Flask(__name__)

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

# ---------------------------------------------------------
# 1. OLD ENGINE: PDF TO COMPRESSED PDF (As it is!)
# ---------------------------------------------------------
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


# ---------------------------------------------------------
# 2. NEW ENGINE: IMAGES TO PDF (With Both Options)
# ---------------------------------------------------------
@app.route('/images_to_pdf', methods=['POST'])
def images_to_pdf():
    if 'files' not in request.files:
        return jsonify({"error": "No files uploaded"}), 400
    
    files = request.files.getlist('files')
    if not files or files[0].filename == '':
        return jsonify({"error": "No files selected"}), 400

    target_kb = int(request.form.get('target_kb', 500))
    total_image_size = 0
    
    new_doc = fitz.open()
    
    # Step 1: Create the ORIGINAL PDF from images
    for file in files:
        img_bytes = file.read()
        total_image_size += len(img_bytes) / 1024
        
        try:
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=100) 
            
            img_pdf_bytes = fitz.open("jpeg", img_byte_arr.getvalue()).convert_to_pdf()
            new_doc.insert_pdf(fitz.open("pdf", img_pdf_bytes))
        except Exception as e:
            print(f"Error processing image: {e}")
            continue

    # Original PDF Bytes
    original_pdf_bytes = new_doc.tobytes(garbage=4, deflate=True)
    generated_pdf_kb = len(original_pdf_bytes) / 1024
    
    # Step 2: Compress the PDF to target size
    pdf_bytes = original_pdf_bytes 
    
    if len(pdf_bytes) / 1024 > target_kb:
        settings = [(1.0, 85), (0.9, 75), (0.8, 65), (0.7, 50)]
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

    # Step 3: Exact Target Size Match (Padding)
    target_size_bytes = int(target_kb * 1024)
    if len(pdf_bytes) < target_size_bytes:
        padding_needed = target_size_bytes - len(pdf_bytes)
        pdf_bytes += b'\0' * padding_needed

    final_kb = len(pdf_bytes) / 1024
    
    # Encode BOTH files
    b64_orig = base64.b64encode(original_pdf_bytes).decode('utf-8')
    b64_comp = base64.b64encode(pdf_bytes).decode('utf-8')

    return jsonify({
        "success": True,
        "original_kb": round(total_image_size, 1),
        "generated_pdf_kb": round(generated_pdf_kb, 1),
        "new_kb": round(final_kb, 1),
        "file_name_orig": "Original_Size_Images.pdf",
        "file_name_comp": "Target_Size_Images.pdf",
        "mime_type": "application/pdf",
        "file_data_orig": b64_orig,
        "file_data_comp": b64_comp
    })

if __name__ == '__main__':
    app.run(debug=True)