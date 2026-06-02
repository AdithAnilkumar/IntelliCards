def segment_document(parsed):
    """
    Segment the parsed document using a 4-level fallback pipeline:
    Level 1: Font Size headings
    Level 2: Bold text elements
    Level 3: Page-by-page splitting
    Level 4: Paragraph-based chunking
    """
    text = parsed.get('text', '')
    pages = parsed.get('pages', [])
    headings = parsed.get('headings', [])
    bold_lines = parsed.get('bold_lines', [])

    if not text.strip():
        return []

    # Clean up delimiters to avoid tiny or noisy chunks
    headings = [h.strip() for h in headings if h.strip() and len(h.strip()) > 3]
    bold_lines = [b.strip() for b in bold_lines if b.strip() and len(b.strip()) > 3]

    # LEVEL 1: Font Size headings
    if headings:
        segments = split_by_delimiters(text, headings, pages)
        if len(segments) > 1:
            return segments

    # LEVEL 2: Bold lines
    if bold_lines:
        segments = split_by_delimiters(text, bold_lines, pages)
        if len(segments) > 1:
            return segments

    # LEVEL 3: Page-by-page Splitting (if multi-page)
    if len(pages) > 1:
        segments = []
        for p in pages:
            p_text = p['text'].strip()
            if not p_text:
                continue
            # Try to guess a topic from the first line of the page
            lines = [l.strip() for l in p_text.split('\n') if l.strip()]
            topic = lines[0][:50] if lines else f"Page {p['page_num']}"
            segments.append({
                'topic': topic,
                'content': p_text,
                'page_num': p['page_num']
            })
        if segments:
            return segments

    # LEVEL 4: Paragraph-based chunking
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    segments = []
    current_chunk = []
    current_len = 0
    chunk_idx = 1

    for para in paragraphs:
        current_chunk.append(para)
        current_len += len(para)
        if current_len >= 1500:
            segments.append({
                'topic': f"Section {chunk_idx}",
                'content': "\n\n".join(current_chunk),
                'page_num': 1
            })
            current_chunk = []
            current_len = 0
            chunk_idx += 1

    if current_chunk:
        segments.append({
            'topic': f"Section {chunk_idx}",
            'content': "\n\n".join(current_chunk),
            'page_num': 1
        })

    return segments


def split_by_delimiters(text, delimiters, pages):
    """
    Split text by a list of delimiters, keeping track of topics and page numbers.
    """
    occurrences = []
    for delim in delimiters:
        start = 0
        while True:
            idx = text.find(delim, start)
            if idx == -1:
                break
            occurrences.append((idx, delim))
            start = idx + len(delim)

    if not occurrences:
        return []

    # Sort occurrences by their position in the text
    occurrences.sort()

    # Filter out overlapping/nested occurrences
    filtered = []
    last_end = -1
    for idx, delim in occurrences:
        if idx >= last_end:
            filtered.append((idx, delim))
            last_end = idx + len(delim)

    if not filtered:
        return []

    segments = []

    # Handle text prior to the first delimiter as Introduction
    if filtered[0][0] > 100:
        intro_content = text[:filtered[0][0]].strip()
        if intro_content:
            segments.append({
                'topic': 'Introduction',
                'content': intro_content,
                'page_num': 1
            })

    for i in range(len(filtered)):
        idx, topic = filtered[i]
        start_content = idx + len(topic)
        end_content = filtered[i + 1][0] if i + 1 < len(filtered) else len(text)
        content = text[start_content:end_content].strip()

        # Try to locate the page number for this topic
        page_num = 1
        for p in pages:
            if topic in p['text']:
                page_num = p['page_num']
                break

        if content:
            segments.append({
                'topic': topic,
                'content': content,
                'page_num': page_num
            })

    return segments
