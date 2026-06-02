import os
import pypdf
import docx

def parse_file(file_path):
    """
    Parse a file based on its extension and extract text, page chunks,
    and metadata about headings/bold lines.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.pdf':
        return parse_pdf(file_path)
    elif ext == '.docx':
        return parse_docx(file_path)
    elif ext in ('.txt', '.md'):
        return parse_txt(file_path)
    else:
        # Fallback to text parsing
        try:
            return parse_txt(file_path)
        except Exception:
            raise ValueError(f"Unsupported file format: {ext}")


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
            line_elements = []
            
            def visitor(text, cm, tm, font_dict, font_size):
                if not text.strip():
                    return
                font_name = ""
                if font_dict and '/BaseFont' in font_dict:
                    font_name = str(font_dict['/BaseFont'])
                is_bold = "bold" in font_name.lower() or "heavy" in font_name.lower() or "black" in font_name.lower()
                y = tm[5]
                line_elements.append((y, font_size, is_bold, text))
            
            page.extract_text(visitor_text=visitor)
            
            if line_elements:
                # Group elements by Y coordinate (top down)
                line_elements.sort(key=lambda x: -x[0])
                grouped_lines = []
                current_y = None
                current_line = []
                
                for y, font_size, is_bold, text in line_elements:
                    if current_y is None:
                        current_y = y
                        current_line = [(font_size, is_bold, text)]
                    elif abs(y - current_y) <= 4:
                        current_line.append((font_size, is_bold, text))
                    else:
                        grouped_lines.append(current_line)
                        current_y = y
                        current_line = [(font_size, is_bold, text)]
                if current_line:
                    grouped_lines.append(current_line)
                
                page_lines_text = []
                for line in grouped_lines:
                    line_text = "".join(part[2] for part in line).strip()
                    if line_text:
                        page_lines_text.append(line_text)
                        
                        # Heuristic: line all bold or large font size
                        all_bold = all(part[1] for part in line)
                        max_size = max(part[0] for part in line)
                        
                        if all_bold and len(line_text) < 100:
                            bold_lines.append(line_text)
                        if max_size > 13.0 and len(line_text) < 100:
                            headings.append(line_text)
                
                txt = "\n".join(page_lines_text)
            else:
                txt = page.extract_text() or ""
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
