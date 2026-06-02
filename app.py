import os
import uuid
from flask import (
    Flask, render_template, request, jsonify,
    session, redirect, url_for, send_file
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# ── Load .env ──────────────────────────────────────────────────────────
load_dotenv()

# ── Import our utilities ───────────────────────────────────────────────
from utils.database import (
    init_db, create_user, get_user_by_username, get_user_by_id,
    create_deck, get_decks_by_user, update_deck_card_count,
    get_flashcards_by_deck, save_flashcards_bulk,
    save_quiz_result, get_quiz_history,
    update_topic_progress, get_topic_progress,
    get_analytics_summary
)
from utils.parser import parse_file
from utils.segmentation import segment_document
from utils.flashcard_generator import generate_flashcards
from utils.quiz_generator import generate_quiz

# ══════════════════════════════════════════════════════════════════════
#  APP CONFIG
# ══════════════════════════════════════════════════════════════════════
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-change-this')

UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt', 'png', 'jpg', 'jpeg'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024   # 16 MB

app.config['UPLOAD_FOLDER']      = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── Initialise DB on startup ───────────────────────────────────────────
init_db()


# ══════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════

def allowed_file(filename):
    """Check the file extension is in the allowed set."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def login_required(f):
    """Simple decorator — redirect to login if no session."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def current_user():
    """Return the logged-in user row, or None."""
    uid = session.get('user_id')
    return get_user_by_id(uid) if uid else None


# ══════════════════════════════════════════════════════════════════════
#  PAGE ROUTES
# ══════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    """Landing page."""
    user = current_user()
    return render_template('index.html', user=user)


@app.route('/dashboard')
@login_required
def dashboard():
    """Analytics dashboard."""
    user = current_user()
    decks = get_decks_by_user(user['id'])
    return render_template('index.html', user=user, decks=decks, page='dashboard')


@app.route('/flashcards/<int:deck_id>')
@login_required
def flashcards(deck_id):
    """Flashcard viewer for a specific deck."""
    user  = current_user()
    cards = get_flashcards_by_deck(deck_id)
    from utils.database import get_connection
    conn = get_connection()
    deck = conn.execute('SELECT * FROM decks WHERE id = ?', (deck_id,)).fetchone()
    conn.close()
    deck_dict = dict(deck) if deck else {}
    return render_template('index.html', user=user, cards=cards,
                           deck_id=deck_id, deck=deck_dict, page='flashcards')


@app.route('/quiz/<int:deck_id>')
@login_required
def quiz(deck_id):
    """Quiz page for a specific deck."""
    user = current_user()
    from utils.database import get_connection
    conn = get_connection()
    deck = conn.execute('SELECT * FROM decks WHERE id = ?', (deck_id,)).fetchone()
    conn.close()
    deck_dict = dict(deck) if deck else {}
    return render_template('index.html', user=user, deck_id=deck_id, deck=deck_dict, page='quiz')


# ══════════════════════════════════════════════════════════════════════
#  AUTH ROUTES
# ══════════════════════════════════════════════════════════════════════

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'GET':
        return render_template('index.html', page='signup')

    data     = request.get_json() or request.form
    username = data.get('username', '').strip()
    email    = data.get('email', '').strip()
    password = data.get('password', '')

    # Basic validation
    if not username or not email or not password:
        return jsonify({'error': 'All fields are required'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    hashed = generate_password_hash(password)
    user_id = create_user(username, email, hashed)

    if user_id is None:
        return jsonify({'error': 'Username or email already exists'}), 409

    session['user_id'] = user_id
    return jsonify({'success': True, 'redirect': url_for('index')})


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('index.html', page='login')

    data     = request.get_json() or request.form
    username = data.get('username', '').strip()
    password = data.get('password', '')

    user = get_user_by_username(username)
    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({'error': 'Invalid username or password'}), 401

    session['user_id'] = user['id']
    return jsonify({'success': True, 'redirect': url_for('index')})


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


# ══════════════════════════════════════════════════════════════════════
#  API — FILE UPLOAD & FLASHCARD GENERATION
# ══════════════════════════════════════════════════════════════════════

@app.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    """
    Receive a file, parse it, segment it, generate flashcards,
    save everything to the DB, and return the new deck id.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not supported'}), 415

    # Save file with a unique name to avoid collisions
    original_name = secure_filename(file.filename)
    unique_name   = f"{uuid.uuid4().hex}_{original_name}"
    file_path     = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
    file.save(file_path)

    try:
        # Step 1 — Parse the file into raw text + metadata
        parsed = parse_file(file_path)

        # Step 2 — Segment into topic chunks using 4-level fallback
        segments = segment_document(parsed)

        # Step 3 — Generate flashcards with GPT-4o
        cards = generate_flashcards(segments)

        if not cards:
            return jsonify({'error': 'No flashcards could be generated'}), 422

        # Step 4 — Save deck + cards to database
        user_id = session['user_id']
        topic   = segments[0]['topic'] if segments else 'General'
        deck_id = create_deck(user_id, unique_name, original_name, topic)
        save_flashcards_bulk(deck_id, cards)
        update_deck_card_count(deck_id, len(cards))

        return jsonify({
            'success':   True,
            'deck_id':   deck_id,
            'card_count': len(cards),
            'topic':     topic
        })

    except Exception as e:
        # Clean up the uploaded file on failure
        if os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════════════
#  API — FLASHCARDS
# ══════════════════════════════════════════════════════════════════════

@app.route('/api/flashcards/<int:deck_id>', methods=['GET'])
@login_required
def api_flashcards(deck_id):
    """Return all flashcards for a deck as JSON."""
    cards = get_flashcards_by_deck(deck_id)
    if not cards:
        return jsonify({'error': 'Deck not found or empty'}), 404
    return jsonify({'cards': cards, 'count': len(cards)})


# ══════════════════════════════════════════════════════════════════════
#  API — QUIZ
# ══════════════════════════════════════════════════════════════════════

@app.route('/api/quiz/<int:deck_id>', methods=['GET'])
@login_required
def api_quiz(deck_id):
    """
    Generate quiz questions from the deck's flashcards.
    Query param: mode = mcq | true_false | fill_blank
    """
    mode  = request.args.get('mode', 'mcq')
    cards = get_flashcards_by_deck(deck_id)
    if not cards:
        return jsonify({'error': 'Deck not found or empty'}), 404

    questions = generate_quiz(cards, mode=mode)
    return jsonify({'questions': questions, 'mode': mode})


@app.route('/api/quiz/submit', methods=['POST'])
@login_required
def submit_quiz():
    """
    Save a completed quiz result and update topic progress.
    Expected JSON: { deck_id, mode, score, total, time_taken, topic_results: [{topic, correct}] }
    """
    data       = request.get_json()
    user_id    = session['user_id']
    deck_id    = data.get('deck_id')
    raw_mode   = data.get('mode', 'mcq')
    if raw_mode == 'tf':
        mode = 'true_false'
    elif raw_mode == 'fill':
        mode = 'fill_blank'
    else:
        mode = raw_mode
    score      = data.get('score', 0)
    total      = data.get('total', 0)
    time_taken = data.get('time_taken')
    topic_results = data.get('topic_results', [])

    save_quiz_result(user_id, deck_id, mode, score, total, time_taken)

    # Update adaptive learning data per topic
    for tr in topic_results:
        update_topic_progress(user_id, tr['topic'], tr['correct'])

    accuracy = round((score / total) * 100) if total else 0
    return jsonify({'success': True, 'accuracy': accuracy})


# ══════════════════════════════════════════════════════════════════════
#  API — ANALYTICS
# ══════════════════════════════════════════════════════════════════════

@app.route('/api/analytics', methods=['GET'])
@login_required
def api_analytics():
    """Return dashboard summary + topic progress for the logged-in user."""
    user_id  = session['user_id']
    summary  = get_analytics_summary(user_id)
    topics   = get_topic_progress(user_id)
    history  = get_quiz_history(user_id, limit=10)
    decks    = get_decks_by_user(user_id)

    return jsonify({
        'summary':      summary,
        'topics':       topics,
        'quiz_history': history,
        'decks':        [dict(d) for d in decks]
    })


# ══════════════════════════════════════════════════════════════════════
#  API — EXPORT
# ══════════════════════════════════════════════════════════════════════

@app.route('/api/export/json/<int:deck_id>', methods=['GET'])
@login_required
def export_json(deck_id):
    """Export a deck's flashcards as a downloadable JSON file."""
    cards = get_flashcards_by_deck(deck_id)
    if not cards:
        return jsonify({'error': 'Deck not found'}), 404

    import json, io
    payload  = json.dumps({'deck_id': deck_id, 'cards': cards}, indent=2)
    buf      = io.BytesIO(payload.encode())
    buf.seek(0)
    return send_file(
        buf,
        mimetype='application/json',
        as_attachment=True,
        download_name=f'intellicards_deck_{deck_id}.json'
    )


@app.route('/api/export/pdf/<int:deck_id>', methods=['GET'])
@login_required
def export_pdf(deck_id):
    """Export a deck's flashcards as a formatted PDF using ReportLab."""
    cards = get_flashcards_by_deck(deck_id)
    if not cards:
        return jsonify({'error': 'Deck not found'}), 404

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        from reportlab.lib.units import cm
        import io

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
                                leftMargin=2*cm, rightMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('title', fontSize=18, fontName='Helvetica-Bold',
                                     spaceAfter=12, textColor=colors.HexColor('#1F497D'))
        q_style = ParagraphStyle('q', fontSize=12, fontName='Helvetica-Bold',
                                 spaceAfter=4, textColor=colors.black)
        a_style = ParagraphStyle('a', fontSize=11, fontName='Helvetica',
                                 spaceAfter=4, textColor=colors.HexColor('#333333'))
        meta_style = ParagraphStyle('meta', fontSize=9, fontName='Helvetica-Oblique',
                                    textColor=colors.grey, spaceAfter=12)

        story = [Paragraph('✦ IntelliCards Export', title_style),
                 Paragraph(f'Total cards: {len(cards)}', meta_style)]

        for i, card in enumerate(cards, 1):
            story.append(Paragraph(f'Q{i}: {card["question"]}', q_style))
            story.append(Paragraph(f'Answer: {card["answer"]}', a_style))
            if card.get('hint'):
                story.append(Paragraph(f'Hint: {card["hint"]}', meta_style))
            story.append(Paragraph(
                f'Difficulty: {card["difficulty"]}  |  Topic: {card["topic"]}', meta_style))
            story.append(HRFlowable(width='100%', thickness=0.5, color=colors.lightgrey))
            story.append(Spacer(1, 0.3*cm))

        doc.build(story)
        buf.seek(0)
        return send_file(buf, mimetype='application/pdf', as_attachment=True,
                         download_name=f'intellicards_deck_{deck_id}.pdf')

    except ImportError:
        return jsonify({'error': 'ReportLab not installed. Run: pip install reportlab'}), 500


# ══════════════════════════════════════════════════════════════════════
#  API — DECKS LIST
# ══════════════════════════════════════════════════════════════════════

@app.route('/api/decks', methods=['GET'])
@login_required
def api_decks():
    """Return all decks for the logged-in user."""
    user_id = session['user_id']
    decks   = get_decks_by_user(user_id)
    return jsonify({'decks': [dict(d) for d in decks]})


# ══════════════════════════════════════════════════════════════════════
#  RUN
# ══════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    app.run(debug=True, port=5000)  