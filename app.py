# app.py
import os
import json
import re
import random
from flask import Flask, request, jsonify, make_response
from dotenv import load_dotenv
import openai

# -------------------------------------------------------------
#                    LOAD ENV & INIT APP
# -------------------------------------------------------------
load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise Exception("OPENAI_API_KEY not found!")

# Инициализация OpenAI с совместимой версией
openai.api_key = API_KEY

app = Flask(__name__)

# Включаем CORS для Android
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# -------------------------------------------------------------
#                    IN-MEMORY TEMPLATES (вместо БД)
# -------------------------------------------------------------
CARD_TEMPLATES = [
    {
        "id": 1,
        "category": "дыхание",
        "base_text": "Сделай {N} глубоких вдохов через нос и медленных выдохов через рот",
        "difficulty": "легко",
        "duration": 120,
        "tags": ["релакс", "офис", "стресс"],
        "language": "RU"
    },
    {
        "id": 2,
        "category": "шея_плечи",
        "base_text": "Повращай плечами {N} раз вперед и {N} раз назад",
        "difficulty": "легко",
        "duration": 180,
        "tags": ["разминка", "офис", "сидячая работа"],
        "language": "RU"
    },
    {
        "id": 3,
        "category": "осанка",
        "base_text": "Выпрями спину и удерживай правильную осанку {N} минут",
        "difficulty": "средне",
        "duration": 300,
        "tags": ["осанка", "работа", "здоровье спины"],
        "language": "RU"
    },
    {
        "id": 4,
        "category": "глаза",
        "base_text": "Отведи взгляд от экрана и сфокусируйся на удаленном объекте {N} секунд",
        "difficulty": "легко",
        "duration": 60,
        "tags": ["зрение", "отдых", "экран"],
        "language": "RU"
    },
    {
        "id": 5,
        "category": "ноги",
        "base_text": "Встань и потянись, подняв руки вверх на {N} секунд",
        "difficulty": "легко",
        "duration": 90,
        "tags": ["разминка", "перерыв", "кровообращение"],
        "language": "RU"
    }
]

EN_TEMPLATES = [
    {
        "id": 6,
        "category": "breathing",
        "base_text": "Take {N} deep breaths through your nose and slow exhales through your mouth",
        "difficulty": "easy",
        "duration": 120,
        "tags": ["relax", "office", "stress"],
        "language": "EN"
    },
    {
        "id": 7,
        "category": "neck_shoulders",
        "base_text": "Rotate your shoulders {N} times forward and {N} times backward",
        "difficulty": "easy",
        "duration": 180,
        "tags": ["warmup", "office", "sitting"],
        "language": "EN"
    },
    {
        "id": 8,
        "category": "posture",
        "base_text": "Straighten your back and maintain correct posture for {N} minutes",
        "difficulty": "medium",
        "duration": 300,
        "tags": ["posture", "work", "back health"],
        "language": "EN"
    }
]

ALL_TEMPLATES = CARD_TEMPLATES + EN_TEMPLATES

# -------------------------------------------------------------
#                    HELPER FUNCTIONS
# -------------------------------------------------------------
def generate_ai_variation(template, user_goal, energy, language):
    """Генерирует вариацию на основе шаблона через OpenAI"""
    
    lang_instruction = "Пиши на русском языке." if language == "RU" else "Write in English."
    n_value = random.randint(3, 10)
    
    prompt = f"""
{lang_instruction}

ИСХОДНЫЙ ШАБЛОН: "{template['base_text']}"
Категория: {template['category']}
Сложность: {template['difficulty']}
Длительность: {template['duration']} секунд

ЦЕЛЬ ПОЛЬЗОВАТЕЛЯ: {user_goal}
УРОВЕНЬ ЭНЕРГИИ: {energy}

Создай 1 вариацию этого упражнения для мобильного приложения:
- Замени {{N}} на число {n_value}
- Сделай текст мотивирующим и дружелюбным
- Сохрани суть упражнения
- Добавь небольшую деталь или совет

Формат ответа ТОЛЬКО JSON:
{{
    "title": "Короткое название (2-4 слова)",
    "description": "Подробная инструкция",
    "duration": число
}}
"""
    
    try:
        # Используем старый API для совместимости
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты создаешь упражнения для приложения здоровья."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=200
        )
        
        raw_response = response.choices[0].message.content
        print(f"AI Response: {raw_response}")
        
        # Парсим JSON
        match = re.search(r"\{.*\}", raw_response, re.DOTALL)
        if match:
            ai_response = json.loads(match.group(0))
            
            return {
                "title": ai_response.get("title", template['category']),
                "description": ai_response.get("description", template['base_text'].replace("{N}", str(n_value))),
                "duration": ai_response.get("duration", template['duration']),
                "is_ai_generated": True
            }
        
    except Exception as e:
        print(f"OpenAI error: {e}")
    
    # Fallback
    return {
        "title": template['category'],
        "description": template['base_text'].replace("{N}", str(n_value)),
        "duration": template['duration'],
        "is_ai_generated": False
    }

# -------------------------------------------------------------
#                    API ENDPOINTS
# -------------------------------------------------------------

# -------------------------------------------------------------
#                  /generate — ОРИГИНАЛЬНЫЙ ENDPOINT
# -------------------------------------------------------------
@app.route("/generate", methods=["POST", "OPTIONS"])
def generate():
    if request.method == "OPTIONS":
        return make_response('', 200)
    
    try:
        data = request.json

        goal = data.get("goal", "Улучшить здоровье")
        energy = data.get("energy", "средняя")
        language = data.get("language", "RU").upper()
        base_meaning = data.get("baseMeaning", "")

        # Language instruction
        lang_instruction = "Пиши текст только на русском языке." if language == "RU" else "Write text only in English."

        # Prompt
        prompt = f"""
Ты пишешь короткие, ёмкие тексты для приложения о здоровье.
{lang_instruction}

Цель пользователя: {goal}
Уровень энергии: {energy}

Верни JSON строго вида:
{{"title": "...", "description": "..."}}
"""

        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Ты генератор коротких текстов."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150,
                temperature=0.8
            )

            raw = response.choices[0].message.content
            print("RAW:", raw)

            # Extract JSON
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                try:
                    obj = json.loads(match.group(0))
                    return jsonify({
                        "success": True,
                        "card": obj
                    })
                except Exception as e:
                    print("JSON parse error:", e)

            # Fallback
            return jsonify({
                "success": True,
                "card": {
                    "title": base_meaning[:40] or "Advice",
                    "description": base_meaning or "Сделай небольшой шаг."
                }
            })

        except Exception as e:
            print("OpenAI error:", e)
            return jsonify({
                "success": True,
                "card": {
                    "title": base_meaning[:40] or "Advice",
                    "description": base_meaning or "Сделай небольшой шаг."
                }
            })

    except Exception as e:
        print("Server error:", e)
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "message": str(e)
        }), 500

# -------------------------------------------------------------
#          POST /api/generate-card — ОСНОВНОЙ ДЛЯ ANDROID
# -------------------------------------------------------------
@app.route("/api/generate-card", methods=["POST", "OPTIONS"])
def generate_card_from_template():
    if request.method == "OPTIONS":
        return make_response('', 200)
    
    try:
        data = request.json
        
        # Параметры
        user_goal = data.get("goal", "Улучшить здоровье")
        category = data.get("category")
        energy = data.get("energy", "средняя")
        language = data.get("language", "RU").upper()
        user_id = data.get("user_id")
        
        # Выбираем шаблоны по языку
        templates = [t for t in ALL_TEMPLATES if t['language'] == language]
        
        if category:
            templates = [t for t in templates if t['category'] == category]
        
        if not templates:
            return jsonify({
                "success": False,
                "error": f"No templates for language: {language}"
            }), 404
        
        # Случайный шаблон
        template = random.choice(templates)
        
        # Генерируем вариацию
        generated = generate_ai_variation(template, user_goal, energy, language)
        
        # Формируем ответ
        response = {
            "success": True,
            "card": {
                "id": template['id'],
                "template_id": template['id'],
                "title": generated['title'],
                "description": generated['description'],
                "category": template['category'],
                "duration": generated['duration'],
                "difficulty": template['difficulty'],
                "tags": template['tags'],
                "language": language,
                "is_ai_generated": generated['is_ai_generated'],
                "energy_level": energy,
                "user_goal": user_goal,
                "created_at": "2024-01-01T00:00:00Z"  # Для совместимости
            }
        }
        
        return jsonify(response)
        
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to generate card",
            "message": str(e)
        }), 500

# -------------------------------------------------------------
#          GET /api/templates — получить шаблоны
# -------------------------------------------------------------
@app.route("/api/templates", methods=["GET"])
def get_templates():
    try:
        language = request.args.get('language', 'RU')
        templates = [t for t in ALL_TEMPLATES if t['language'] == language]
        
        return jsonify({
            "success": True,
            "count": len(templates),
            "templates": templates
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# -------------------------------------------------------------
#                  HEALTH CHECK
# -------------------------------------------------------------
@app.route("/")
def root():
    return jsonify({
        "status": "habit-ai-server running",
        "version": "2.0",
        "templates_count": len(ALL_TEMPLATES),
        "endpoints": {
            "GET /": "Health check",
            "POST /generate": "Legacy OpenAI generation",
            "POST /api/generate-card": "Generate from templates (for Android)",
            "GET /api/templates": "Get all templates"
        }
    })

# -------------------------------------------------------------
#                       RUN APP
# -------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"🚀 Starting server on port {port}")
    print(f"📋 Templates loaded: {len(ALL_TEMPLATES)}")
    print(f"🔑 OpenAI API Key: {'Loaded' if API_KEY else 'Missing'}")
    app.run(host="0.0.0.0", port=port, debug=True)
