import sqlite3
import os

# Path to the database file — sits in the project root
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database.db')


def get_connection():
    """Return a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # lets you access columns by name
    return conn


def init_db():
    """Create all tables if they don't already exist."""
    conn = get_connection()
    c = conn.cursor()

    # ── Users ──────────────────────────────────────────────────────────
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    UNIQUE NOT NULL,
            email         TEXT    UNIQUE NOT NULL,
            password_hash TEXT    NOT NULL,
            created_at    TEXT    DEFAULT (datetime('now'))
        )
    ''')

    # ── Uploaded files / decks ─────────────────────────────────────────
    c.execute('''
        CREATE TABLE IF NOT EXISTS decks (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            filename     TEXT    NOT NULL,
            original_name TEXT   NOT NULL,
            topic        TEXT,
            card_count   INTEGER DEFAULT 0,
            created_at   TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # ── Flashcards ─────────────────────────────────────────────────────
    c.execute('''
        CREATE TABLE IF NOT EXISTS flashcards (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            deck_id    INTEGER NOT NULL,
            question   TEXT    NOT NULL,
            answer     TEXT    NOT NULL,
            difficulty TEXT    CHECK(difficulty IN ('easy','medium','hard')) DEFAULT 'medium',
            hint       TEXT,
            example    TEXT,
            topic      TEXT,
            created_at TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (deck_id) REFERENCES decks(id)
        )
    ''')

    # ── Quiz results ───────────────────────────────────────────────────
    c.execute('''
        CREATE TABLE IF NOT EXISTS quiz_results (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            deck_id      INTEGER NOT NULL,
            mode         TEXT    CHECK(mode IN ('mcq','true_false','fill_blank')),
            score        INTEGER NOT NULL,
            total        INTEGER NOT NULL,
            time_taken   INTEGER,                  -- seconds
            created_at   TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (user_id)  REFERENCES users(id),
            FOREIGN KEY (deck_id)  REFERENCES decks(id)
        )
    ''')

    # ── Per-topic accuracy (for adaptive learning) ─────────────────────
    c.execute('''
        CREATE TABLE IF NOT EXISTS topic_progress (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            topic         TEXT    NOT NULL,
            correct       INTEGER DEFAULT 0,
            incorrect     INTEGER DEFAULT 0,
            last_reviewed TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    conn.commit()
    conn.close()
    print("* Database initialised at:", DB_PATH)


# ═══════════════════════════════════════════════════════════════════════
#  USER HELPERS
# ═══════════════════════════════════════════════════════════════════════

def create_user(username, email, password_hash):
    """Insert a new user. Returns the new user id."""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
            (username, email, password_hash)
        )
        conn.commit()
        return c.lastrowid
    except sqlite3.IntegrityError:
        return None          # username or email already exists
    finally:
        conn.close()


def get_user_by_username(username):
    """Return a user row by username, or None."""
    conn = get_connection()
    row = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    return row


def get_user_by_id(user_id):
    """Return a user row by id, or None."""
    conn = get_connection()
    row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return row


# ═══════════════════════════════════════════════════════════════════════
#  DECK HELPERS
# ═══════════════════════════════════════════════════════════════════════

def create_deck(user_id, filename, original_name, topic=''):
    """Insert a new deck and return its id."""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        'INSERT INTO decks (user_id, filename, original_name, topic) VALUES (?, ?, ?, ?)',
        (user_id, filename, original_name, topic)
    )
    conn.commit()
    deck_id = c.lastrowid
    conn.close()
    return deck_id


def get_decks_by_user(user_id):
    """Return all decks belonging to a user."""
    conn = get_connection()
    rows = conn.execute(
        'SELECT * FROM decks WHERE user_id = ? ORDER BY created_at DESC', (user_id,)
    ).fetchall()
    conn.close()
    return rows


def update_deck_card_count(deck_id, count):
    """Update how many cards are in a deck."""
    conn = get_connection()
    conn.execute('UPDATE decks SET card_count = ? WHERE id = ?', (count, deck_id))
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════
#  FLASHCARD HELPERS
# ═══════════════════════════════════════════════════════════════════════

def save_flashcard(deck_id, question, answer, difficulty, hint, example, topic):
    """Insert one flashcard and return its id."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO flashcards (deck_id, question, answer, difficulty, hint, example, topic)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (deck_id, question, answer, difficulty, hint, example, topic))
    conn.commit()
    card_id = c.lastrowid
    conn.close()
    return card_id


def save_flashcards_bulk(deck_id, cards: list):
    """
    Insert many flashcards at once.
    cards = list of dicts with keys: question, answer, difficulty, hint, example, topic
    """
    conn = get_connection()
    conn.executemany('''
        INSERT INTO flashcards (deck_id, question, answer, difficulty, hint, example, topic)
        VALUES (:deck_id, :question, :answer, :difficulty, :hint, :example, :topic)
    ''', [{**c, 'deck_id': deck_id} for c in cards])
    conn.commit()
    conn.close()


def get_flashcards_by_deck(deck_id):
    """Return all flashcards for a deck as a list of dicts."""
    conn = get_connection()
    rows = conn.execute(
        'SELECT * FROM flashcards WHERE deck_id = ? ORDER BY id', (deck_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_flashcards_by_topic(deck_id, topic):
    """Return flashcards filtered by topic."""
    conn = get_connection()
    rows = conn.execute(
        'SELECT * FROM flashcards WHERE deck_id = ? AND topic = ?', (deck_id, topic)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════
#  QUIZ HELPERS
# ═══════════════════════════════════════════════════════════════════════

def save_quiz_result(user_id, deck_id, mode, score, total, time_taken=None):
    """Save a completed quiz result."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO quiz_results (user_id, deck_id, mode, score, total, time_taken)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, deck_id, mode, score, total, time_taken))
    conn.commit()
    conn.close()


def get_quiz_history(user_id, limit=20):
    """Return recent quiz results for a user."""
    conn = get_connection()
    rows = conn.execute('''
        SELECT qr.*, d.original_name
        FROM quiz_results qr
        JOIN decks d ON qr.deck_id = d.id
        WHERE qr.user_id = ?
        ORDER BY qr.created_at DESC
        LIMIT ?
    ''', (user_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════
#  TOPIC PROGRESS / ADAPTIVE LEARNING
# ═══════════════════════════════════════════════════════════════════════

def update_topic_progress(user_id, topic, correct: bool):
    """
    Increment correct or incorrect count for a topic.
    Creates the row if it doesn't exist yet.
    """
    conn = get_connection()
    existing = conn.execute(
        'SELECT id FROM topic_progress WHERE user_id = ? AND topic = ?',
        (user_id, topic)
    ).fetchone()

    if existing:
        if correct:
            conn.execute('''
                UPDATE topic_progress
                SET correct = correct + 1, last_reviewed = datetime('now')
                WHERE user_id = ? AND topic = ?
            ''', (user_id, topic))
        else:
            conn.execute('''
                UPDATE topic_progress
                SET incorrect = incorrect + 1, last_reviewed = datetime('now')
                WHERE user_id = ? AND topic = ?
            ''', (user_id, topic))
    else:
        conn.execute('''
            INSERT INTO topic_progress (user_id, topic, correct, incorrect)
            VALUES (?, ?, ?, ?)
        ''', (user_id, topic, 1 if correct else 0, 0 if correct else 1))

    conn.commit()
    conn.close()


def get_topic_progress(user_id):
    """
    Return all topic progress for a user, with accuracy % calculated.
    Sorted weakest first.
    """
    conn = get_connection()
    rows = conn.execute(
        'SELECT * FROM topic_progress WHERE user_id = ? ORDER BY last_reviewed DESC',
        (user_id,)
    ).fetchall()
    conn.close()

    result = []
    for r in rows:
        total = r['correct'] + r['incorrect']
        accuracy = round((r['correct'] / total) * 100) if total > 0 else 0
        result.append({
            'topic':     r['topic'],
            'correct':   r['correct'],
            'incorrect': r['incorrect'],
            'total':     total,
            'accuracy':  accuracy
        })

    # Sort weakest topics first
    result.sort(key=lambda x: x['accuracy'])
    return result


# ═══════════════════════════════════════════════════════════════════════
#  ANALYTICS SUMMARY
# ═══════════════════════════════════════════════════════════════════════

def get_analytics_summary(user_id):
    """
    Return a summary dict used by the dashboard:
    total cards, quizzes, overall accuracy, streak (placeholder).
    """
    conn = get_connection()

    # Total flashcards across all user decks
    total_cards = conn.execute('''
        SELECT COALESCE(SUM(card_count), 0)
        FROM decks WHERE user_id = ?
    ''', (user_id,)).fetchone()[0]

    # Total quizzes
    total_quizzes = conn.execute(
        'SELECT COUNT(*) FROM quiz_results WHERE user_id = ?', (user_id,)
    ).fetchone()[0]

    # Overall accuracy
    acc_row = conn.execute('''
        SELECT SUM(score), SUM(total)
        FROM quiz_results WHERE user_id = ?
    ''', (user_id,)).fetchone()
    overall_accuracy = 0
    if acc_row[1] and acc_row[1] > 0:
        overall_accuracy = round((acc_row[0] / acc_row[1]) * 100)

    # Last 7 days accuracy (for bar chart)
    daily = conn.execute('''
        SELECT DATE(created_at) as day,
               ROUND(SUM(score) * 100.0 / SUM(total)) as accuracy
        FROM quiz_results
        WHERE user_id = ?
          AND created_at >= DATE('now', '-7 days')
        GROUP BY day
        ORDER BY day ASC
    ''', (user_id,)).fetchall()

    conn.close()

    return {
        'total_cards':      total_cards,
        'total_quizzes':    total_quizzes,
        'overall_accuracy': overall_accuracy,
        'daily_accuracy':   [dict(r) for r in daily],
    }


# ═══════════════════════════════════════════════════════════════════════
#  RUN DIRECTLY TO INITIALISE
# ═══════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    init_db()