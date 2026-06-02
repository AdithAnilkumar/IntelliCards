import os
import pypdf
import docx
import re

def clean_extracted_text(text):
    if not text:
        return ""
    
    # 1. Merge spaced-out letters (e.g. "I s o q u a n t" -> "Isoquant")
    # Must be done BEFORE consolidating spaces to preserve double spaces as word boundaries.
    text = re.sub(r'\b[a-zA-Z](?: [a-zA-Z])+\b', lambda m: m.group(0).replace(' ', ''), text)

    # 2. Clean multiple spaces/tabs
    text = re.sub(r'[ \t]+', ' ', text)
    
    # 3. OCR and typing corrections
    corrections = [
        (r'\boutoout\b', 'output'),
        (r'\boutout\b', 'output'),
        (r'\boutut\b', 'output'),
        (r'\boutoout(\d+)\b', r'output \1'),
        (r'\boutout(\d+)\b', r'output \1'),
        (r'\boutut(\d+)\b', r'output \1'),
        (r'\bproccess\b', 'process'),
        (r'\bproccesses\b', 'processes'),
        (r'\bproceses\b', 'processes'),
        (r'\bteh\b', 'the'),
        (r'\btehm\b', 'them'),
        (r'\bsamee\b', 'same'),
        (r'\binteresect\b', 'intersect'),
        (r'\binteresects\b', 'intersects'),
        (r'\binteresecing\b', 'intersecting'),
        (r'\binteresecting\b', 'intersecting'),
        (r'\bgives combinations\b', 'given combinations'),
    ]
    for pattern, replacement in corrections:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def parse_file(file_path):
    """
    Parse a file based on its extension and extract text, page chunks,
    and metadata about headings/bold lines.
    """
    ext = os.path.splitext(file_path)[1].lower()
    res = None
    if ext == '.pdf':
        res = parse_pdf(file_path)
    elif ext == '.docx':
        res = parse_docx(file_path)
    elif ext in ('.txt', '.md'):
        res = parse_txt(file_path)
    else:
        # Fallback to text parsing
        try:
            res = parse_txt(file_path)
        except Exception:
            raise ValueError(f"Unsupported file format: {ext}")
            
    if res:
        res['text'] = clean_extracted_text(res['text'])
        for page in res.get('pages', []):
            page['text'] = clean_extracted_text(page['text'])
        res['bold_lines'] = [clean_extracted_text(b) for b in res.get('bold_lines', []) if b.strip()]
        res['headings'] = [clean_extracted_text(h) for h in res.get('headings', []) if h.strip()]
        
    return res


def parse_pdf(file_path):
    reader = pypdf.PdfReader(file_path)
    pages_data = []
    bold_lines = []
    headings = []
    full_text_list = []

    for idx, page in enumerate(reader.pages):
        page_num = idx + 1
        txt = ""
        try:
            # 1. Extract clean layout-preserved text directly using pypdf's standard layout engine
            txt = page.extract_text() or ""
            
            # 2. Use visitor only to collect metadata for bold lines and headings
            def visitor(text, cm, tm, font_dict, font_size):
                if not text.strip():
                    return
                # Ignore duplicate container blocks (often representing entire page layers)
                if len(text) > 200 or '\n' in text:
                    return
                font_name = ""
                if font_dict and '/BaseFont' in font_dict:
                    font_name = str(font_dict['/BaseFont'])
                is_bold = "bold" in font_name.lower() or "heavy" in font_name.lower() or "black" in font_name.lower()
                clean_t = text.strip()
                if is_bold and len(clean_t) < 100:
                    bold_lines.append(clean_t)
                if font_size > 13.0 and len(clean_t) < 100:
                    headings.append(clean_t)
            
            page.extract_text(visitor_text=visitor)
        except Exception:
            txt = page.extract_text() or ""
            
        pages_data.append({'page_num': page_num, 'text': txt})
        full_text_list.append(txt)

    return {
        'text': "\n\n".join(full_text_list),
        'pages': pages_data,
        'bold_lines': list(set(bold_lines)),
        'headings': list(set(headings))
    }


def parse_docx(file_path):
    doc = docx.Document(file_path)
    full_text_list = []
    bold_lines = []
    headings = []
    
    pages_data = []
    current_page_text = []
    paragraph_count = 0
    page_num = 1
    
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        
        full_text_list.append(text)
        current_page_text.append(text)
        paragraph_count += 1
        
        is_heading_style = para.style.name.startswith('Heading')
        is_bold_para = False
        
        if para.runs:
            is_bold_para = all(run.bold for run in para.runs if run.text.strip())
            
        if is_heading_style and len(text) < 100:
            headings.append(text)
        elif is_bold_para and len(text) < 100:
            bold_lines.append(text)
            
        if paragraph_count >= 20:
            pages_data.append({
                'page_num': page_num,
                'text': "\n".join(current_page_text)
            })
            current_page_text = []
            paragraph_count = 0
            page_num += 1
            
    if current_page_text:
        pages_data.append({
            'page_num': page_num,
            'text': "\n".join(current_page_text)
        })
        
    return {
        'text': "\n\n".join(full_text_list),
        'pages': pages_data,
        'bold_lines': list(set(bold_lines)),
        'headings': list(set(headings))
    }


def parse_txt(file_path):
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()
        
    lines = text.split('\n')
    pages_data = []
    current_page_lines = []
    current_char_count = 0
    page_num = 1
    headings = []
    
    for line in lines:
        cleaned_line = line.strip()
        if not cleaned_line:
            continue
            
        if cleaned_line.isupper() and len(cleaned_line) < 80:
            headings.append(cleaned_line)
            
        current_page_lines.append(cleaned_line)
        current_char_count += len(cleaned_line)
        
        if current_char_count >= 3000:
            pages_data.append({
                'page_num': page_num,
                'text': "\n".join(current_page_lines)
            })
            current_page_lines = []
            current_char_count = 0
            page_num += 1
            
    if current_page_lines:
        pages_data.append({
            'page_num': page_num,
            'text': "\n".join(current_page_lines)
        })
        
    return {
        'text': text,
        'pages': pages_data,
        'bold_lines': [],
        'headings': headings
    }
