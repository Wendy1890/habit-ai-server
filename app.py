# app.py
import os
import json
import re
import random
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime

# -------------------------------------------------------------
#                    LOAD ENV & INIT APP
# -------------------------------------------------------------
load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise Exception("OPENAI_API_KEY not found!")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)

# -------------------------------------------------------------
#                    DATABASE CONFIG (Railway PostgreSQL)
# -------------------------------------------------------------
# Railway предоставляет DATABASE_URL в переменных окружения
DATABASE_URL = os.getenv('DATABASE_URL')

if DATABASE_URL:
    # Конвертируем postgres:// в postgresql:// для SQLAlchemy
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    print(f"Using Railway PostgreSQL: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL}")
else:
    # Для локальной разработки
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cards.db'
    print("Using SQLite for local development")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# -------------------------------------------------------------
#                    DATABASE MODELS
# -------------------------------------------------------------
class CardTemplate(db.Model):
    __tablename__ = 'card_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(100), nullable=False)           # "дыхание", "шея_плечи", "осанка"
    base_text = db.Column(db.Text, nullable=False)                 # Шаблонный текст с {N}
    variations_count = db.Column(db.Integer, default=3)            # Сколько вариаций генерировать
    difficulty = db.Column(db.String(50), default='легко')         # "легко", "средне", "сложно"
    duration_seconds = db.Column(db.Integer, default=300)          # Длительность в секундах
    tags = db.Column(db.String(500), default='')                   # Теги через запятую
    language = db.Column(db.String(10), default='RU')              # "RU", "EN", "DE"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'category': self.category,
            'base_text': self.base_text,
            'difficulty': self.difficulty,
            'duration': self.duration_seconds,
            'tags': self.tags.split(',') if self.tags else [],
            'language': self.language,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class GeneratedCard(db.Model):
    __tablename__ = 'generated_cards'
    
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('card_templates.id'), nullable=False)
    user_id = db.Column(db.String(100), nullable=True)                    # Идентификатор пользователя
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    difficulty = db.Column(db.String(50), nullable=False)
    tags = db.Column(db.String(500), default='')
    language = db.Column(db.String(10), default='RU')
    is_ai_generated = db.Column(db.Boolean, default=True)
    energy_level = db.Column(db.String(50))                               # Уровень энергии пользователя
    user_goal = db.Column(db.String(200))                                 # Цель пользователя
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Связь с шаблоном
    template = db.relationship('CardTemplate', backref=db.backref('generations', lazy=True))
    
    def to_dict(self):
        return {
            'id': self.id,
            'template_id': self.template_id,
            'title': self.title,
            'description': self.description,
            'category': self.category,
            'duration': self.duration,
            'difficulty': self.difficulty,
            'tags': self.tags.split(',') if self.tags else [],
            'language': self.language,
            'is_ai_generated': self.is_ai_generated,
            'energy_level': self.energy_level,
            'user_goal': self.user_goal,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

# -------------------------------------------------------------
#                    INIT DATABASE
# -------------------------------------------------------------
@app.before_request
def setup_database():
    """Создаем таблицы при первом запросе"""
    try:
        db.create_all()
        
        # Добавляем демо-шаблоны если таблица пустая
        if CardTemplate.query.count() == 0:
            add_sample_templates()
            print("Added sample templates to database")
    except Exception as e:
        print(f"Database setup error: {e}")

def add_sample_templates():
    """Добавляем примеры шаблонов в БД"""
    sample_templates = [
        # Русские шаблоны
        CardTemplate(
            category="дыхание",
            base_text="Сделай {N} глубоких вдохов через нос и медленных выдохов через рот. Сосредоточься на дыхании.",
            variations_count=5,
            difficulty="легко",
            duration_seconds=120,
            tags="релакс,офис,стресс,фокус",
            language="RU"
        ),
        CardTemplate(
            category="шея_плечи",
            base_text="Повращай плечами {N} раз вперед и {N} раз назад. Расслабь мышцы шеи.",
            variations_count=4,
            difficulty="легко",
            duration_seconds=180,
            tags="разминка,офис,сидячая работа,напряжение",
            language="RU"
        ),
        CardTemplate(
            category="осанка",
            base_text="Выпрями спину, опусти плечи и удерживай правильную осанку {N} минут.",
            variations_count=3,
            difficulty="средне",
            duration_seconds=300,
            tags="осанка,работа,здоровье спины,привычка",
            language="RU"
        ),
        CardTemplate(
            category="глаза",
            base_text="Отведи взгляд от экрана и сфокусируйся на удаленном объекте {N} секунд. Поморгай {N} раз.",
            variations_count=4,
            difficulty="легко",
            duration_seconds=60,
            tags="зрение,отдых,экран,усталость глаз",
            language="RU"
        ),
        CardTemplate(
            category="ноги",
            base_text="Встань и потянись, подняв руки вверх на {N} секунд. Сделай {N} приседаний.",
            variations_count=3,
            difficulty="легко",
            duration_seconds=90,
            tags="разминка,перерыв,кровообращение,энергия",
            language="RU"
        ),
        CardTemplate(
            category="фокус",
            base_text="Закрой глаза и сосредоточься на дыхании {N} секунд. Очисти мысли.",
            variations_count=4,
            difficulty="легко",
            duration_seconds=90,
            tags="медитация,фокус,ментальное здоровье,перезагрузка",
            language="RU"
        ),
        
        # Английские шаблоны
        CardTemplate(
            category="breathing",
            base_text="Take {N} deep breaths through your nose and slow exhales through your mouth. Focus on your breathing.",
            variations_count=5,
            difficulty="easy",
            duration_seconds=120,
            tags="relax,office,stress,focus",
            language="EN"
        ),
        CardTemplate(
            category="neck_shoulders",
            base_text="Rotate your shoulders {N} times forward and {N} times backward. Relax your neck muscles.",
            variations_count=4,
            difficulty="easy",
            duration_seconds=180,
            tags="warmup,office,sitting,tension",
            language="EN"
        ),
        CardTemplate(
            category="posture",
            base_text="Straighten your back, lower your shoulders and maintain correct posture for {N} minutes.",
            variations_count=3,
            difficulty="medium",
            duration_seconds=300,
            tags="posture,work,back health,habit",
            language="EN"
        )
    ]
    
    for template in sample_templates:
        db.session.add(template)
    
    db.session.commit()

# -------------------------------------------------------------
#                    HELPER FUNCTIONS
# -------------------------------------------------------------
def generate_ai_variation(template, user_goal, energy, language):
    """Генерирует вариацию на основе шаблона через OpenAI"""
    
    lang_instruction = "Пиши на русском языке." if language == "RU" else "Write in English."
    
    prompt = f"""
{lang_instruction}

ORIGINAL TEMPLATE: "{template.base_text}"
Category: {template.category}
Difficulty: {template.difficulty}
Duration: {template.duration_seconds} seconds
Tags: {template.tags}

USER CONTEXT:
Goal: {user_goal}
Energy level: {energy}

TASK:
Create 1 variation of this exercise for a health app.
- Replace {{N}} with specific numbers (between 3 and 10)
- Make the wording more engaging and motivating
- Keep the essence of the exercise
- Add a small detail or tip
- Keep it concise

Respond ONLY in JSON format:
{{
    "title": "Short title (3-5 words)",
    "description": "Detailed description with instructions",
    "duration": number_in_seconds,
    "difficulty": "easy/medium/hard"
}}
"""
    
    try:
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",  # Можно использовать "gpt-4" если доступен
            messages=[
                {
                    "role": "system", 
                    "content": "You are a health app assistant. You create exercise variations based on templates."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=250
        )
        
        raw_response = completion.choices[0].message.content
        print(f"AI Raw Response: {raw_response}")
        
        # Парсим JSON из ответа
        match = re.search(r"\{.*\}", raw_response, re.DOTALL)
        if match:
            ai_response = json.loads(match.group(0))
            
            return {
                "title": ai_response.get("title", template.category),
                "description": ai_response.get("description", template.base_text),
                "duration": ai_response.get("duration", template.duration_seconds),
                "difficulty": ai_response.get("difficulty", template.difficulty),
                "is_ai_generated": True
            }
        
    except Exception as e:
        print(f"OpenAI generation error: {e}")
    
    # Fallback: простая замена {N} на число
    n_value = random.randint(3, 10)
    base_with_number = template.base_text.replace("{N}", str(n_value))
    
    return {
        "title": template.category,
        "description": base_with_number,
        "duration": template.duration_seconds,
        "difficulty": template.difficulty,
        "is_ai_generated": False
    }

# -------------------------------------------------------------
#                    API ENDPOINTS
# -------------------------------------------------------------

# -------------------------------------------------------------
#                  /generate — ОРИГИНАЛЬНЫЙ ENDPOINT (сохраняем)
# -------------------------------------------------------------
@app.route("/generate", methods=["POST"])
def generate():
    try:
        data = request.json

        action_type = data.get("actionType")
        goal = data.get("goal")
        energy = data.get("energy")
        engagement = data.get("engagement")
        session_type = data.get("sessionType")
        base_meaning = data.get("baseMeaning", "")
        language = data.get("language", "RU")

        # -------- Language instruction --------
        lang_instruction = (
            "Пиши текст только на русском языке."
            if language.upper() == "RU"
            else "Write text only in English."
        )

        # -------- Prompt --------
        prompt = f"""
Ты пишешь короткие, ёмкие тексты для приложения о здоровье.
{lang_instruction}

Дано:
- Тип действия: {action_type}
- Цель пользователя: {goal}
- Энергия: {energy}
- Вовлечённость: {engagement}
- Спец-режим: {session_type}
- Базовый смысл: {base_meaning}

Верни JSON строго вида:
{{"title": "...", "description": "..."}}
"""

        # -----------------------------------------------------
        #                 OPENAI REQUEST
        # -----------------------------------------------------
        try:
            completion = client.chat.completions.create(
                model="gpt-3.5-turbo",  # Изменено с gpt-5.1 на доступную модель
                messages=[
                    {"role": "system", "content": "Ты генератор коротких текстов."},
                    {"role": "user", "content": prompt}
                ],
                max_completion_tokens=150,
                temperature=0.8
            )

            raw = completion.choices[0].message.content
            print("RAW:", raw)

            # Try extracting JSON via regex
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                try:
                    obj = json.loads(match.group(0))
                    return jsonify(obj)
                except Exception as e:
                    print("JSON PARSE ERROR:", e)

            # fallback
            return jsonify({
                "title": base_meaning[:40] or "Advice",
                "description": base_meaning or "Сделай небольшой шаг."
            })

        except Exception as e:
            print("OPENAI ERROR:", e)
            return jsonify({
                "title": base_meaning[:40] or "Advice",
                "description": base_meaning or "Сделай небольшой шаг."
            })

    except Exception as e:
        print("SERVER ERROR:", e)
        return jsonify({
            "title": "Error",
            "description": "Internal server error"
        })

# -------------------------------------------------------------
#          GET /api/templates — получить все шаблоны
# -------------------------------------------------------------
@app.route("/api/templates", methods=["GET"])
def get_templates():
    try:
        language = request.args.get('language', 'RU')
        templates = CardTemplate.query.filter_by(language=language).all()
        
        return jsonify({
            "success": True,
            "count": len(templates),
            "templates": [t.to_dict() for t in templates]
        })
    except Exception as e:
        print(f"Error getting templates: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# -------------------------------------------------------------
#     GET /api/templates/<category> — шаблоны по категории
# -------------------------------------------------------------
@app.route("/api/templates/<category>", methods=["GET"])
def get_templates_by_category(category):
    try:
        language = request.args.get('language', 'RU')
        templates = CardTemplate.query.filter_by(
            category=category, 
            language=language
        ).all()
        
        return jsonify({
            "success": True,
            "category": category,
            "count": len(templates),
            "templates": [t.to_dict() for t in templates]
        })
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# -------------------------------------------------------------
#          POST /api/generate-card — генерация на основе шаблонов
# -------------------------------------------------------------
@app.route("/api/generate-card", methods=["POST"])
def generate_card_from_template():
    try:
        data = request.json
        
        # Параметры от Android
        user_goal = data.get("goal", "Улучшить здоровье")
        category = data.get("category")  # опционально: конкретная категория
        energy = data.get("energy", "средняя")
        language = data.get("language", "RU").upper()
        user_id = data.get("user_id")   # опционально: идентификатор пользователя
        
        # Выбираем подходящие шаблоны
        query = CardTemplate.query.filter_by(language=language)
        
        if category:
            query = query.filter_by(category=category)
        
        templates = query.all()
        
        if not templates:
            return jsonify({
                "success": False,
                "error": f"No templates found for language: {language}"
            }), 404
        
        # Выбираем случайный шаблон
        template = random.choice(templates)
        
        # Генерируем вариацию
        generated_data = generate_ai_variation(template, user_goal, energy, language)
        
        # Сохраняем в БД
        generated_card = GeneratedCard(
            template_id=template.id,
            user_id=user_id,
            title=generated_data["title"],
            description=generated_data["description"],
            category=template.category,
            duration=generated_data["duration"],
            difficulty=generated_data["difficulty"],
            tags=template.tags,
            language=language,
            is_ai_generated=generated_data["is_ai_generated"],
            energy_level=energy,
            user_goal=user_goal
        )
        
        db.session.add(generated_card)
        db.session.commit()
        
        response_data = {
            "success": True,
            "card": generated_card.to_dict()
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"Error generating card: {e}")
        db.session.rollback()
        
        return jsonify({
            "success": False,
            "error": "Failed to generate card",
            "message": str(e)
        }), 500

# -------------------------------------------------------------
#     GET /api/generated-cards — история сгенерированных карточек
# -------------------------------------------------------------
@app.route("/api/generated-cards", methods=["GET"])
def get_generated_cards():
    try:
        user_id = request.args.get('user_id')
        limit = int(request.args.get('limit', 20))
        
        query = GeneratedCard.query.order_by(GeneratedCard.created_at.desc())
        
        if user_id:
            query = query.filter_by(user_id=user_id)
        
        cards = query.limit(limit).all()
        
        return jsonify({
            "success": True,
            "count": len(cards),
            "cards": [card.to_dict() for card in cards]
        })
    except Exception as e:
        print(f"Error getting generated cards: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# -------------------------------------------------------------
#           POST /api/templates — добавить новый шаблон
# -------------------------------------------------------------
@app.route("/api/templates", methods=["POST"])
def add_template():
    try:
        data = request.json
        
        required_fields = ['category', 'base_text', 'language']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    "success": False,
                    "error": f"Missing required field: {field}"
                }), 400
        
        new_template = CardTemplate(
            category=data['category'],
            base_text=data['base_text'],
            variations_count=data.get('variations_count', 3),
            difficulty=data.get('difficulty', 'легко'),
            duration_seconds=data.get('duration_seconds', 300),
            tags=data.get('tags', ''),
            language=data['language']
        )
        
        db.session.add(new_template)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Template added successfully",
            "template": new_template.to_dict()
        })
        
    except Exception as e:
        print(f"Error adding template: {e}")
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# -------------------------------------------------------------
#                  HEALTH CHECK & ROOT
# -------------------------------------------------------------
@app.route("/")
def root():
    db_status = "connected" if db.session.bind else "disconnected"
    templates_count = CardTemplate.query.count()
    generated_count = GeneratedCard.query.count()
    
    return {
        "status": "habit-ai-server running",
        "database": db_status,
        "templates_count": templates_count,
        "generated_cards_count": generated_count,
        "endpoints": {
            "GET /": "This health check",
            "POST /generate": "Original OpenAI generation",
            "GET /api/templates": "Get all templates",
            "POST /api/generate-card": "Generate card from templates",
            "GET /api/generated-cards": "Get generated cards history",
            "POST /api/templates": "Add new template"
        }
    }

# -------------------------------------------------------------
#                       RUN APP
# -------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"Starting server on port {port}")
    print(f"Database: {app.config['SQLALCHEMY_DATABASE_URI']}")
    app.run(host="0.0.0.0", port=port)
