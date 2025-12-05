# app.py - БЕЗ БД для быстрого старта
import os
import json
import re
import random
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import openai

# -------------------------------------------------------------
#                    LOAD ENV & INIT APP
# -------------------------------------------------------------
load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise Exception("OPENAI_API_KEY not found!")

openai.api_key = API_KEY
app = Flask(__name__)
CORS(app)

# Простые шаблоны в памяти
TEMPLATES = [
    {
        "id": 1,
        "category": "дыхание",
        "base_text": "Сделай {N} глубоких вдохов через нос и медленных выдохов через рот",
        "difficulty": "легко",
        "duration": 120,
        "language": "RU"
    },
    {
        "id": 2,
        "category": "шея_плечи",
        "base_text": "Повращай плечами {N} раз вперед и {N} раз назад",
        "difficulty": "легко",
        "duration": 180,
        "language": "RU"
    },
    {
        "id": 3,
        "category": "осанка",
        "base_text": "Выпрями спину и удерживай правильную осанку {N} минут",
        "difficulty": "средне",
        "duration": 300,
        "language": "RU"
    }
]

# -------------------------------------------------------------
#                    HELPER FUNCTIONS
# -------------------------------------------------------------
def generate_card_from_template(goal, language="RU"):
    """Генерирует карточку на основе шаблона"""
    
    # Выбираем шаблон
    templates = [t for t in TEMPLATES if t["language"] == language]
    if not templates:
        return {
            "title": "Нет шаблонов",
            "description": f"Помни о цели: {goal}",
            "duration": 300,
            "category": "общее"
        }
    
    template = random.choice(templates)
    n_value = random.randint(3, 10)
    
    # Простая генерация без OpenAI для начала
    description = template["base_text"].replace("{N}", str(n_value))
    
    return {
        "id": random.randint(1000, 9999),
        "template_id": template["id"],
        "title": template["category"],
        "description": description,
        "category": template["category"],
        "duration": template["duration"],
        "difficulty": template["difficulty"],
        "language": language,
        "is_ai_generated": False,
        "user_goal": goal
    }

# -------------------------------------------------------------
#                    API ENDPOINTS
# -------------------------------------------------------------

@app.route("/")
def health():
    return jsonify({
        "status": "🚀 Server is running",
        "version": "1.0",
        "templates_count": len(TEMPLATES),
        "endpoints": {
            "POST /api/generate": "Generate card",
            "GET /api/templates": "Get templates",
            "POST /generate": "Legacy OpenAI endpoint"
        }
    })

@app.route("/api/generate", methods=["POST"])
def generate():
    try:
        data = request.json
        goal = data.get("goal", "Улучшить здоровье")
        language = data.get("language", "RU")
        
        card = generate_card_from_template(goal, language)
        
        return jsonify({
            "success": True,
            "card": card
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/templates", methods=["GET"])
def get_templates():
    language = request.args.get("language", "RU")
    templates = [t for t in TEMPLATES if t["language"] == language]
    
    return jsonify({
        "success": True,
        "templates": templates
    })

@app.route("/generate", methods=["POST"])
def legacy_generate():
    try:
        data = request.json
        goal = data.get("goal", "Улучшить здоровье")
        language = data.get("language", "RU")
        
        prompt = f"""
{'Пиши на русском' if language == 'RU' else 'Write in English'}

Цель пользователя: {goal}

Создай короткое упражнение для мобильного приложения.
Верни JSON: {{"title": "...", "description": "..."}}
"""
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты создаешь упражнения."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=150
        )
        
        raw = response.choices[0].message.content
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        
        if match:
            data = json.loads(match.group(0))
            return jsonify(data)
        else:
            return jsonify({
                "title": "Упражнение",
                "description": f"Помни о цели: {goal}"
            })
            
    except Exception as e:
        return jsonify({
            "title": "Ошибка",
            "description": str(e)
        }), 500

# -------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"✅ Server starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
