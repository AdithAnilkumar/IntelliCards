import os
import json
import re
import requests

def generate_flashcards(segments):
    """
    Generate flashcards from document segments. Uses OpenAI GPT-4o if a valid
    API key is present, otherwise falls back to a rule-based generator.
    """
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    
    if not api_key or api_key == "sk-your-key-here":
        print("* OpenAI API Key not set or placeholder. Using rule-based fallback generator.")
        return generate_flashcards_fallback(segments)
        
    try:
        return generate_flashcards_ai(segments, api_key)
    except Exception as e:
        print(f"* AI generation failed ({e}). Falling back to rule-based generator.")
        return generate_flashcards_fallback(segments)


def generate_flashcards_ai(segments, api_key):
    """
    Generate flashcards using OpenAI's GPT-4o with JSON Mode.
    """
    all_cards = []
    
    for seg in segments:
        topic = seg['topic']
        content = seg['content']
        
        # Skip very short content
        if len(content.strip()) < 50:
            continue
            
        system_prompt = (
            "You are an expert AI educator. Your task is to analyze the provided educational text "
            "and generate high-quality study flashcards.\n\n"
            "You MUST respond with a JSON object in this exact schema:\n"
            "{\n"
            "  \"flashcards\": [\n"
            "    {\n"
            "      \"question\": \"Clear, concise question testing a single concept.\",\n"
            "      \"answer\": \"Accurate, detailed answer to the question.\",\n"
            "      \"difficulty\": \"easy\" | \"medium\" | \"hard\",\n"
            "      \"hint\": \"A helpful clue or tip that doesn't directly reveal the answer.\",\n"
            "      \"example\": \"A code snippet, practical example, or real-world use case illustrating the concept.\",\n"
            "      \"topic\": \"The main topic of this card.\"\n"
            "    }\n"
            "  ]\n"
            "}"
        )
        
        user_prompt = f"Topic: {topic}\nContent:\n{content}"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "gpt-4o",
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3
        }
        
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            res_data = response.json()
            raw_content = res_data['choices'][0]['message']['content']
            cards_json = json.loads(raw_content)
            
            for card in cards_json.get("flashcards", []):
                all_cards.append({
                    "question": card.get("question", "N/A"),
                    "answer": card.get("answer", "N/A"),
                    "difficulty": card.get("difficulty", "medium").lower() if card.get("difficulty", "medium").lower() in ('easy', 'medium', 'hard') else 'medium',
                    "hint": card.get("hint", ""),
                    "example": card.get("example", ""),
                    "topic": card.get("topic", topic)
                })
        else:
            print(f"OpenAI API returned status code {response.status_code}: {response.text}")
            raise Exception("Failed api call")
            
    return all_cards


def generate_flashcards_fallback(segments):
    """
    Rule-based fallback flashcard generator. Analyzes text structure,
    colons, and definition keywords to generate high-quality conceptual cards.
    """
    all_cards = []
    
    for seg in segments:
        topic = seg['topic']
        content = seg['content']
        
        # Split content into paragraphs
        paragraphs = [p.strip() for p in content.split('\n') if p.strip()]
        
        for para in paragraphs:
            # Skip very short sentences/headings
            if len(para) < 20:
                continue
                
            # Pattern 1: Colon split (e.g. "Term: Definition")
            if ":" in para and 3 < para.find(":") < 60:
                parts = para.split(":", 1)
                term = parts[0].strip()
                defn = parts[1].strip()
                
                # Normalize capitalization and period
                if defn and not defn[0].isupper():
                    defn = defn[0].upper() + defn[1:]
                if defn and not defn.endswith('.'):
                    defn += '.'
                
                # Check for example text in the definition
                example = ""
                ex_match = re.search(r'(?:for example|e\.g\.|example:)(.*?)(?:\.|$)', defn, re.IGNORECASE)
                if ex_match:
                    example = ex_match.group(0).strip()
                    
                clean_term = term.replace('_', ' ').replace('-', ' ').strip()
                
                all_cards.append({
                    "question": f"Describe the concept and definition of '{clean_term}' as it applies to {topic}.",
                    "answer": defn,
                    "difficulty": "easy" if len(defn) < 100 else "medium",
                    "hint": f"Think about how '{clean_term.lower()}' functions or its primary purpose.",
                    "example": example or f"// Application of {clean_term}: In practice, this represents a core element of {topic}.",
                    "topic": topic
                })
                continue
                
            # Pattern 2: Definition keywords ("is defined as", "refers to", "is a", "are defined as", "means")
            keywords = ["is defined as", "refers to", "is a", "are defined as", "means"]
            matched_keyword = None
            kw_idx = -1
            for kw in keywords:
                idx = para.lower().find(kw)
                if 2 <= idx < len(para) - 10:  # Allow short terms (>=2 characters)
                    matched_keyword = kw
                    kw_idx = idx
                    break
                        
            if matched_keyword:
                term = para[:kw_idx].strip()
                defn = para[kw_idx:].strip()
                
                # Normalize full sentence format
                full_sentence = f"{term} {defn}"
                if full_sentence and not full_sentence[0].isupper():
                    full_sentence = full_sentence[0].upper() + full_sentence[1:]
                if full_sentence and not full_sentence.endswith('.'):
                    full_sentence += '.'
                
                example = ""
                ex_match = re.search(r'(?:for example|e\.g\.|example:)(.*?)(?:\.|$)', defn, re.IGNORECASE)
                if ex_match:
                    example = ex_match.group(0).strip()
                
                # Formulate distinct question types based on the keyword
                clean_term = term.replace('_', ' ').replace('-', ' ').strip()
                if matched_keyword == "means":
                    question = f"What is the literal meaning and significance of the term '{clean_term}' in the context of {topic}?"
                elif matched_keyword in ("refers to", "is defined as"):
                    question = f"What does the term '{clean_term}' refer to in {topic}, and how is it defined?"
                else:
                    question = f"Explain the role and definition of '{clean_term}' within the context of {topic}."

                all_cards.append({
                    "question": question,
                    "answer": full_sentence,
                    "difficulty": "medium",
                    "hint": f"Consider the term '{clean_term.lower()}' and its literal description.",
                    "example": example or f"// Real-world application of {clean_term} in {topic}",
                    "topic": topic
                })
                continue
                
            # Pattern 3: Question from general paragraph
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', para) if s.strip()]
            if sentences:
                q_term = sentences[0]
                if len(q_term) > 10 and len(q_term) < 150:
                    if len(sentences) > 1:
                        # Multi-sentence paragraph
                        answer = " ".join(sentences[1:])
                        all_cards.append({
                            "question": f"Regarding {topic}: {q_term} Explain the details or implications of this statement.",
                            "answer": answer,
                            "difficulty": "hard",
                            "hint": f"Focuses on the core concept: '{q_term[:30]}...'",
                            "example": f"// Case study: Explains how this principle operates in {topic}.",
                            "topic": topic
                        })
                    else:
                        # Single-sentence paragraph: Check for conditional rules
                        cond_match = re.match(r'^(When|If) (.*?), (.*?)(?:\.|$)', q_term, re.IGNORECASE)
                        if cond_match:
                            word = cond_match.group(1).capitalize() # "When" or "If"
                            x_part = cond_match.group(2).strip()
                            y_part = cond_match.group(3).strip()
                            
                            # Standardize first letter of y_part
                            if y_part:
                                y_part = y_part[0].lower() + y_part[1:]
                                
                            all_cards.append({
                                "question": f"Regarding {topic}: What is the effect on '{y_part}' {word.lower()} {x_part}?",
                                "answer": q_term,
                                "difficulty": "medium",
                                "hint": f"Think about the causal link: {x_part} leads to {y_part}.",
                                "example": f"// Relationship rule: {x_part} => {y_part}",
                                "topic": topic
                            })
                        else:
                            # Standard general single-sentence fallback
                            all_cards.append({
                                "question": f"Discuss the core concept and implications of this statement in '{topic}':\n\"{q_term}\"",
                                "answer": f"In the context of {topic}, this statement outlines that: {q_term}",
                                "difficulty": "medium",
                                "hint": "Think about the broader context of this topic.",
                                "example": f"// Key takeaway for {topic}",
                                "topic": topic
                            })
                            
    # Ensure we return at least some cards
    if not all_cards:
        # Absolute fallback if no patterns matched
        all_cards.append({
            "question": f"What is the main subject discussed under '{topic}'?",
            "answer": segments[0]['content'][:300] if segments else "No content available.",
            "difficulty": "medium",
            "hint": "Check the introductory text.",
            "example": "",
            "topic": topic
        })
        
    return all_cards
