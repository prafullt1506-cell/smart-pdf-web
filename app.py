from flask import Flask, request, render_template, jsonify, send_file
import fitz
import io
import os
import zipfile
import base64
import tempfile
import gc  # 🛡️ RAM Optimization
import subprocess
import platform
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
    try:
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

            try:
                doc = fitz.open(stream=original_bytes, filetype="pdf")
                if doc.is_encrypted:
                     return jsonify({"error": f"File {filename} is encrypted. Unlock it first."}), 400
            except Exception as e:
                return jsonify({"error": f"Invalid or corrupted PDF: {filename}"}), 400

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

            # (Removed Padding Logic: Corrupts files and adds no value.)
            
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
    except Exception as e:
        return jsonify({"error": f"Compression Error: {str(e)}"}), 500
    finally:
        gc.collect()

# ==========================================
# 🖼️ ENGINE 2: IMAGES TO PDF
# ==========================================
@app.route('/images_to_pdf', methods=['POST'])
def images_to_pdf():
    try:
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
            except Exception as e:
                continue

        if len(new_doc) == 0:
            return jsonify({"error": "No valid images found to convert."}), 400

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

        # (Removed Padding Logic: Corrupts files and adds no value.)

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
    except Exception as e:
         return jsonify({"error": f"Image to PDF Error: {str(e)}"}), 500
    finally:
        gc.collect()

# ==========================================
# 📄 ENGINE 3: PDF TO IMAGES (ZIP)
# ==========================================
@app.route('/pdf_to_images', methods=['POST'])
def pdf_to_images():
    try:
        if 'files' not in request.files:
            return jsonify({"error": "No files uploaded"}), 400
        files = request.files.getlist('files')
        file = files[0]
        pdf_bytes = file.read()
        total_original_kb = len(pdf_bytes) / 1024
        
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            if doc.is_encrypted:
                return jsonify({"error": "File is encrypted. Unlock it first."}), 400
        except Exception:
             return jsonify({"error": "Invalid or corrupted PDF file."}), 400

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
    except Exception as e:
        return jsonify({"error": f"PDF to Images Error: {str(e)}"}), 500
    finally:
        gc.collect()

# ==========================================
# 📝 ENGINE 4: PDF TO WORD (.docx)
# ==========================================
@app.route('/pdf_to_word', methods=['POST'])
def pdf_to_word():
    try:
        file = request.files['files']
        original_kb = len(file.read()) / 1024
        file.seek(0)
        
        temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        temp_docx = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
        
        file.save(temp_pdf.name)
        
        # Verify PDF is valid before converting
        try:
             doc_check = fitz.open(temp_pdf.name)
             if doc_check.is_encrypted:
                 doc_check.close()
                 return jsonify({"error": "File is encrypted. Unlock it first."}), 400
             doc_check.close()
        except:
             return jsonify({"error": "Invalid PDF format."}), 400

        cv = Converter(temp_pdf.name)
        cv.convert(temp_docx.name, start=0, end=None)
        cv.close()
        
        with open(temp_docx.name, 'rb') as f:
            docx_bytes = f.read()
        b64_data = base64.b64encode(docx_bytes).decode('utf-8')
        
        return jsonify({
            "success": True,
            "original_kb": round(original_kb, 1),
            "new_kb": round(len(docx_bytes) / 1024, 1),
            "file_name": "Converted.docx",
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "file_data": b64_data
        })
    except Exception as e:
         return jsonify({"error": f"PDF to Word Error: {str(e)}"}), 500
    finally:
        if os.path.exists(temp_pdf.name): os.remove(temp_pdf.name)
        if os.path.exists(temp_docx.name): os.remove(temp_docx.name)
        gc.collect()

# ==========================================
# 📑 ENGINE 5: WORD TO PDF (Advanced Pro Version with Fallback)
# ==========================================
@app.route('/word_to_pdf', methods=['POST'])
def word_to_pdf():
    try:
        if 'files' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
            
        file = request.files['files']
        original_kb = len(file.read()) / 1024
        file.seek(0)
        
        # Create temp files
        temp_dir = tempfile.gettempdir()
        temp_docx = tempfile.NamedTemporaryFile(delete=False, suffix=".docx", dir=temp_dir)
        file.save(temp_docx.name)
        temp_pdf_name = temp_docx.name.replace(".docx", ".pdf")
        
        # 1. Try Advanced High-Quality Conversion (LibreOffice)
        conversion_success = False
        command = 'libreoffice'
        if platform.system() == 'Windows':
            command = 'soffice' # Windows command
        elif platform.system() == 'Darwin':
            command = '/Applications/LibreOffice.app/Contents/MacOS/soffice' # Mac command
            
        try:
            # Run background LibreOffice converter
            subprocess.run([
                command, '--headless', '--convert-to', 'pdf', '--outdir', temp_dir, temp_docx.name
            ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            if os.path.exists(temp_pdf_name):
                conversion_success = True
                with open(temp_pdf_name, 'rb') as f:
                    pdf_bytes = f.read()
        except Exception as e:
            print(f"LibreOffice failed or not installed. Fallback to basic engine. Error: {e}")
            
        # 2. Fallback to Basic Text Extraction (If LibreOffice fails/missing)
        if not conversion_success:
            doc = Document(temp_docx.name)
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
        return jsonify({"error": f"Word to PDF Error: {str(e)}"}), 500
    finally:
        # Cleanup ALL temp files safely
        if 'temp_docx' in locals() and os.path.exists(temp_docx.name):
            try: os.remove(temp_docx.name)
            except: pass
        if 'temp_pdf_name' in locals() and os.path.exists(temp_pdf_name):
            try: os.remove(temp_pdf_name)
            except: pass
        gc.collect()

# ==========================================
# 📂 ENGINE 6: MERGE MULTIPLE PDFs
# ==========================================
@app.route('/merge_pdfs', methods=['POST'])
def merge_pdfs():
    try:
        files = request.files.getlist('files')
        if not files:
            return jsonify({"error": "No files uploaded"}), 400

        new_doc = fitz.open()
        total_input_kb = 0

        for file in files:
            pdf_bytes = file.read()
            total_input_kb += len(pdf_bytes) / 1024
            try:
                src_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                if src_doc.is_encrypted:
                    new_doc.close()
                    return jsonify({"error": f"File {file.filename} is encrypted. Cannot merge."}), 400
                new_doc.insert_pdf(src_doc)
                src_doc.close()
            except Exception as e:
                new_doc.close()
                return jsonify({"error": f"Error merging {file.filename}: {str(e)}"}), 400

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
    except Exception as e:
         return jsonify({"error": f"Merge Error: {str(e)}"}), 500
    finally:
        gc.collect()

# ==========================================
# ✂️ ENGINE 7: SPLIT PDF
# ==========================================
@app.route('/split_pdf', methods=['POST'])
def split_pdf():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        file = request.files['file']
        pages_str = request.form.get('pages', '')
        
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
                    
        try:
             doc = fitz.open(stream=pdf_bytes, filetype="pdf")
             if doc.is_encrypted:
                 return jsonify({"error": "File is encrypted. Unlock it first."}), 400
        except:
             return jsonify({"error": "Invalid or corrupted PDF file."}), 400

        valid_pages = [p for p in sorted(list(pages_to_keep)) if 0 <= p <= len(doc)-1]
        if not valid_pages:
            doc.close()
            return jsonify({"error": "Selected pages do not exist in the PDF"}), 400
            
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
        return jsonify({"error": f"Split Error: {str(e)}"}), 500
    finally:
        gc.collect()

# ==========================================
# 🔐 ENGINE 8: PROTECT & UNLOCK PDF
# ==========================================
@app.route('/protect_pdf', methods=['POST'])
def protect_pdf():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        file = request.files['file']
        password = request.form.get('password', '')
        mode = request.form.get('mode', 'protect')
        
        if not password:
            return jsonify({"error": "Password is required"}), 400
            
        pdf_bytes = file.read()
        original_kb = len(pdf_bytes) / 1024
        
        try:
             doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except:
             return jsonify({"error": "Invalid or corrupted PDF file."}), 400
        
        if mode == 'protect':
            if doc.is_encrypted:
                doc.close()
                return jsonify({"error": "This PDF is already protected!"}), 400
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
                    doc.close()
                    return jsonify({"error": "Incorrect password! Could not unlock PDF."}), 400
                out_bytes = doc.tobytes(garbage=4, deflate=True)
                out_filename = "Unlocked_" + secure_filename(file.filename)
            else:
                doc.close()
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
        return jsonify({"error": f"Security Engine Error: {str(e)}"}), 500
    finally:
        gc.collect()

# ==========================================
# ✂️🖼️ ENGINE 9: PRO IMAGE CROPPER & ENHANCER
# ==========================================
@app.route('/process-image-crop', methods=['POST'])
def process_image_crop():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
            
        file = request.files['file']
        
        try:
             img = Image.open(file)
        except:
             return jsonify({'error': 'Invalid image format uploaded.'}), 400
        
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

        # 3. Dynamic Unit Resolution Target Parser
        unit = request.form.get('unit', 'px')
        raw_w = request.form.get('target_w', '')
        raw_h = request.form.get('target_h', '')
        raw_dpi = request.form.get('target_dpi', '')

        try:
            target_dpi = int(raw_dpi) if raw_dpi else 300
        except ValueError:
            target_dpi = 300

        target_w, target_h = None, None
        if raw_w and raw_h:
            try:
                if unit == 'cm':
                    target_w = int((float(raw_w) / 2.54) * target_dpi)
                    target_h = int((float(raw_h) / 2.54) * target_dpi)
                else:
                    target_w = int(float(raw_w))
                    target_h = int(float(raw_h))
            except ValueError:
                pass

        if target_w and target_h and target_w > 0 and target_h > 0:
            img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

        # 4. Byte Clamping Compression (Safe Mode and Strict Size Mode hybrid)
        target_kb = request.form.get('target_kb')
        comp_mode = request.form.get('comp_mode', 'safe') # 🚀 UI मधून Safe किंवा Strict मोड घेईल
        img_byte_arr = io.BytesIO()
        
        if target_kb and target_kb.isdigit():
            target_bytes = int(target_kb) * 1024
            quality = 95
            while quality > 15:
                img_byte_arr.seek(0)
                img_byte_arr.truncate()
                img.save(img_byte_arr, format=original_format, quality=quality, optimize=True, dpi=(target_dpi, target_dpi))
                if img_byte_arr.tell() <= target_bytes:
                    break
                quality -= 5
                
            # 🚀 STRICT MODE LOGIC: जर फाईल टार्गेटपेक्षा लहान असेल, तर कचरा (Zero bytes) भरून साईझ तंतोतंत वाढवा
            if comp_mode == 'strict':
                current_size = img_byte_arr.tell()
                if current_size < target_bytes:
                    img_byte_arr.write(b'\0' * (target_bytes - current_size))
        else:
            img.save(img_byte_arr, format=original_format, quality=95, optimize=True, dpi=(target_dpi, target_dpi))

        img_byte_arr.seek(0)
        return send_file(img_byte_arr, mimetype=f'image/{original_format.lower()}', as_attachment=True, download_name=f"Edited_Image.{original_format.lower()}")

    except Exception as e:
        print("Error System Core Grid Failure:", e)
        return jsonify({'error': f"Image Processing Error: {str(e)}"}), 500
    finally:
        gc.collect()

if __name__ == '__main__':
    app.run(debug=True)
