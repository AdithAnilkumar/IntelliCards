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
    
    # We will process segments in batches or individually to stay within limits
    # and keep mapping to specific topics. Let's do them individually.
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
                # Ensure fields are present and valid
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
    colons, and definition keywords to generate cards.
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
            if ":" in para and 10 < para.find(":") < 60:
                parts = para.split(":", 1)
                term = parts[0].strip()
                defn = parts[1].strip()
                
                # Check for example text in the definition
                example = ""
                ex_match = re.search(r'(?:for example|e\.g\.|example:)(.*?)(?:\.|$)', defn, re.IGNORECASE)
                if ex_match:
                    example = ex_match.group(0).strip()
                    
                all_cards.append({
                    "question": f"What is the definition of '{term}' in the context of {topic}?",
                    "answer": defn,
                    "difficulty": "easy" if len(defn) < 100 else "medium",
                    "hint": f"It is related to {term.lower()}.",
                    "example": example or f"// Example of {term}",
                    "topic": topic
                })
                continue
                
            # Pattern 2: Definition keywords ("is defined as", "refers to", "is a type of")
            keywords = ["is defined as", "refers to", "is a", "are defined as", "means"]
            matched_keyword = None
            for kw in keywords:
                if kw in para.lower():
                    # Ensure keyword isn't at the very start or end
                    kw_idx = para.lower().find(kw)
                    if 5 < kw_idx < len(para) - 15:
                        matched_keyword = kw
                        break
                        
            if matched_keyword:
                kw_idx = para.lower().find(matched_keyword)
                term = para[:kw_idx].strip()
                defn = para[kw_idx:].strip()
                
                example = ""
                ex_match = re.search(r'(?:for example|e\.g\.|example:)(.*?)(?:\.|$)', defn, re.IGNORECASE)
                if ex_match:
                    example = ex_match.group(0).strip()
                    
                all_cards.append({
                    "question": f"Explain '{term}' as it relates to {topic}.",
                    "answer": defn,
                    "difficulty": "medium",
                    "hint": f"Consider the term '{term.lower()}'.",
                    "example": example or f"// Concept application for {term}",
                    "topic": topic
                })
                continue
                
            # Pattern 3: Question from general paragraph
            # We just split by sentence, make the first sentence the core question prompt
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', para) if s.strip()]
            if sentences:
                q_term = sentences[0]
                if len(q_term) > 10 and len(q_term) < 100:
                    answer = " ".join(sentences[1:]) if len(sentences) > 1 else para
                    all_cards.append({
                        "question": f"Regarding {topic}: {q_term}",
                        "answer": answer,
                        "difficulty": "hard",
                        "hint": f"Focuses on: {q_term[:30]}...",
                        "example": f"// Application of {topic} concept",
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
