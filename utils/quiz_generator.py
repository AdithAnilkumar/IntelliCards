import random
import re

def generate_quiz(cards, mode='mcq'):
    """
    Generate quiz questions from flashcards.
    Supports mode='mcq' (Multiple Choice), 'tf'/'true_false' (True/False),
    and 'fill'/'fill_blank' (Fill in the Blank).
    """
    if not cards:
        return []

    # Standardize mode names
    if mode in ('mcq', 'multiple_choice'):
        return generate_mcq_quiz(cards)
    elif mode in ('tf', 'true_false'):
        return generate_tf_quiz(cards)
    elif mode in ('fill', 'fill_blank'):
        return generate_fill_blank_quiz(cards)
    else:
        return generate_mcq_quiz(cards)


def generate_mcq_quiz(cards):
    questions = []
    
    # Collect all answers to use as distractors
    all_answers = [c['answer'] for c in cards]
    
    for idx, card in enumerate(cards):
        correct_answer = card['answer']
        question_text = card['question']
        
        # Get other answers as distractors
        distractors = [ans for ans in all_answers if ans != correct_answer]
        distractors = list(set(distractors)) # Remove duplicates
        
        # If not enough distractors in the deck, add generic ones
        if len(distractors) < 3:
            generic_distractors = [
                "It is a scheduling state constraint.",
                "It represents the memory overhead of the kernel.",
                "None of the above options are correct.",
                "It refers to the disk I/O scheduling window."
            ]
            for gd in generic_distractors:
                if gd not in distractors and gd != correct_answer:
                    distractors.append(gd)
                    
        # Randomly choose 3 distractors
        chosen_distractors = random.sample(distractors, min(3, len(distractors)))
        
        # Combine and shuffle options
        options = [correct_answer] + chosen_distractors
        random.shuffle(options)
        
        correct_index = options.index(correct_answer)
        
        questions.append({
            'card_id': card.get('id'),
            'question': question_text,
            'options': options,
            'correct_index': correct_index,
            'topic': card.get('topic', 'General'),
            'hint': card.get('hint', '')
        })
        
    random.shuffle(questions)
    return questions


def generate_tf_quiz(cards):
    questions = []
    
    for idx, card in enumerate(cards):
        # We can either make it a True statement or a False statement
        is_true_statement = random.choice([True, False])
        
        if is_true_statement:
            question_text = f"True or False: {card['question']}?\nStatement: {card['answer']}"
            correct_answer = "True"
        else:
            # Swap with another card's answer to make a false statement
            other_cards = [c for c in cards if c['answer'] != card['answer']]
            if other_cards:
                wrong_card = random.choice(other_cards)
                question_text = f"True or False: {card['question']}?\nStatement: {wrong_card['answer']}"
            else:
                # Fallback if only 1 card exists
                question_text = f"True or False: {card['question']}?\nStatement: An incorrect variation of the process concept."
            correct_answer = "False"
            
        questions.append({
            'card_id': card.get('id'),
            'question': question_text,
            'options': ["True", "False"],
            'correct_index': 0 if correct_answer == "True" else 1,
            'topic': card.get('topic', 'General'),
            'hint': card.get('hint', '')
        })
        
    random.shuffle(questions)
    return questions


def generate_fill_blank_quiz(cards):
    questions = []
    
    for idx, card in enumerate(cards):
        answer = card['answer']
        # Try to find a good noun or keyword to blank out.
        # Find capitalized words or common terms.
        # Let's extract words of length > 4 that are nouns/concepts.
        words = re.findall(r'\b[a-zA-Z]{5,}\b', answer)
        
        if words:
            # Avoid blanking common stop words if possible
            stop_words = {'about', 'their', 'there', 'would', 'could', 'should', 'which', 'other', 'these'}
            filtered_words = [w for w in words if w.lower() not in stop_words]
            blank_word = random.choice(filtered_words if filtered_words else words)
            
            # Replace the word with a blank
            # Case insensitive replace of first occurrence
            pattern = re.compile(re.escape(blank_word), re.IGNORECASE)
            question_text = pattern.sub("________", answer, count=1)
            question_text = f"Complete the statement by filling in the blank:\n{question_text}"
            
            questions.append({
                'card_id': card.get('id'),
                'question': question_text,
                'correct_answer': blank_word,
                # Give options as hint/scaffolding or leave as text input.
                # In standard web apps, fill in the blank can have options or input.
                # Let's provide 4 options including the correct word to make it accessible.
                'options': generate_blank_options(blank_word),
                'correct_index': 0, # Will be shuffled
                'topic': card.get('topic', 'General'),
                'hint': card.get('hint', '')
            })
            
    # For each question, shuffle its options
    for q in questions:
        correct_word = q['correct_answer']
        options = q['options']
        random.shuffle(options)
        q['correct_index'] = options.index(correct_word)
        del q['correct_answer']
        
    random.shuffle(questions)
    return questions


def generate_blank_options(correct_word):
    # Generates distractor options for the fill in the blank word
    distractors = [
        "Constraint", "Scheduling", "Overhead", "Pipeline", "Protocol",
        "Framework", "Interface", "Algorithm", "Variable", "Execution"
    ]
    # Filter to matching capitalization
    is_cap = correct_word[0].isupper() if correct_word else False
    
    options = [correct_word]
    for d in distractors:
        word = d if is_cap else d.lower()
        if word != correct_word and word not in options:
            options.append(word)
        if len(options) >= 4:
            break
            
    # Fill up to 4 if needed
    while len(options) < 4:
        dummy = f"option_{len(options)}"
        options.append(dummy if is_cap else dummy.lower())
        
    return options
