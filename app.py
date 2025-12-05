import os
import json
import re
import random
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from dotenv import load_dotenv
import openai
from datetime import datetime

# -------------------------------------------------------------
#                    LOAD ENV & INIT APP
# -------------------------------------------------------------
load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise Exception("OPENAI_API_KEY not found!")

openai.api_key = API_KEY
app = Flask(__name__)
CORS(app)  # Включаем CORS для Android

# -------------------------------------------------------------
#                    DATABASE CONFIG (Railway PostgreSQL)
# -------------------------------------------------------------
DATABASE_URL = os.getenv('DATABASE_URL', '')

if DATABASE_URL:
    # Конвертируем для SQLAlchemy
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    print(f"✅ Using PostgreSQL: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'Connected'}")
else:
    # Fallback to SQLite (для локальной разработки)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cards.db'
    print("⚠️ Using SQLite (no DATABASE_URL found)")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# -------------------------------------------------------------
#                    DATABASE MODELS
# -------------------------------------------------------------
class CardTemplate(db.Model):
    __tablename__ = 'card_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(100), nullable=False)
    base_text = db.Column(db.Text, nullable=False)
    difficulty = db.Column(db.String(50), default='легко')
    duration = db.Column(db.Integer, default=300)
    tags = db.Column(db.String(500), default='')
    language = db.Column(db.String(10), default='RU')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'category': self.category,
            'base_text': self.base_text,
            'difficulty': self.difficulty,
            'duration': self.duration,
            'tags': self.tags.split(',') if self.tags else [],
            'language': self.language,
            'created_at': self.created_at.isoformat()
        }

class GeneratedCard(db.Model):
    __tablename__ = 'generated_cards'
    
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    difficulty = db.Column(db.String(50), nullable=False)
    language = db.Column(db.String(10), default='RU')
    is_ai_generated = db.Column(db.Boolean, default=True)
    user_goal = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'template_id': self.template_id,
            'title': self.title,
            'description': self.description,
            'category': self.category,
            'duration': self.duration,
            'difficulty': self.difficulty,
            'language': self.language,
            'is_ai_generated': self.is_ai_generated,
            'user_goal': self.user_goal,
            'created_at': self.created_at.isoformat()
        }

# -------------------------------------------------------------
#                    INIT DATABASE
# -------------------------------------------------------------
with app.app_context():
    db.create_all()
    
    # Добавляем демо-шаблоны если таблица пустая
    if CardTemplate.query.count() == 0:
        add_sample_templates()
        print("✅ Added sample templates to database")

def add_sample_templates():
    """Добавляем примеры шаблонов в БД"""
    samples = [
        CardTemplate(
            category="дыхание",
            base_text="Сделай {N} глубоких вдохов через нос и медленных выдохов через рот",
            difficulty="легко",
            duration=120,
            tags="релакс,офис,стресс",
            language="RU"
        ),
        CardTemplate(
            category="шея_плечи",
            base_text="Повращай плечами {N} раз вперед и {N} раз назад",
            difficulty="легко",
            duration=180,
            tags="разминка,офис,сидячая работа",
            language="RU"
        ),
        CardTemplate(
            category="осанка",
            base_text="Выпрями спину и удерживай правильную осанку {N} минут",
            difficulty="средне",
            duration=300,
            tags="осанка,работа,здоровье спины",
            language="RU"
        ),
        CardTemplate(
            category="глаза",
            base_text="Отведи взгляд от экрана и сфокусируйся на удаленном объекте {N} секунд",
            difficulty="легко",
            duration=60,
            tags="зрение,отдых,экран",
            language="RU"
        )
    ]
    
    for sample in samples:
        db.session.add(sample)
    
    db.session.commit()

# -------------------------------------------------------------
#                    HELPER FUNCTIONS
# -------------------------------------------------------------
def generate_with_openai(template, goal, energy, language):
    """Генерирует вариацию через OpenAI"""
    
    lang_text = "русском" if language == "RU" else "английском"
    n_value = random.randint(3, 10)
    
    prompt = f"""
Напиши на {lang_text} языке.

Шаблон упражнения: "{template.base_text}"
Категория: {template.category}
Длительность: {template.duration} секунд

Цель пользователя: {goal}
Уровень энергии: {energy}

Создай интересную вариацию этого упражнения:
- Используй число {n_value} вместо {{N}}
- Сделай текст мотивирующим
- Добавь полезный совет

Формат JSON:
{{
    "title": "Короткое название",
    "description": "Полное описание",
    "duration": число
}}
"""
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты создаешь упражнения для приложения здоровья."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=200
        )
        
        raw = response.choices[0].message.content
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        
        if match:
            data = json.loads(match.group(0))
            return {
                "title": data.get("title", template.category),
                "description": data.get("description", template.base_text.replace("{N}", str(n_value))),
                "duration": data.get("duration", template.duration),
                "is_ai_generated": True
            }
            
    except Exception as e:
        print(f"OpenAI error: {e}")
    
    # Fallback
    return {
        "title": template.category,
        "description": template.base_text.replace("{N}", str(random.randint(3, 10))),
        "duration": template.duration,
        "is_ai_generated": False
    }

# -------------------------------------------------------------
#                    API ENDPOINTS
# -------------------------------------------------------------

@app.route("/")
def health():
    templates_count = CardTemplate.query.count()
    generated_count = GeneratedCard.query.count()
    
    return jsonify({
        "status": "🚀 Server is running",
        "database": "PostgreSQL" if DATABASE_URL else "SQLite",
        "templates": templates_count,
        "generated_cards": generated_count
    })

# Основной endpoint для Android
@app.route("/api/generate", methods=["POST"])
def generate_card():
    try:
        data = request.json
        goal = data.get("goal", "Улучшить здоровье")
        language = data.get("language", "RU")
        
        # Получаем случайный шаблон из БД
        templates = CardTemplate.query.filter_by(language=language).all()
        if not templates:
            return jsonify({
                "success": False,
                "error": "No templates found"
            }), 404
        
        template = random.choice(templates)
        
        # Генерируем через OpenAI
        generated = generate_with_openai(template, goal, "medium", language)
        
        # Сохраняем в БД
        new_card = GeneratedCard(
            template_id=template.id,
            title=generated["title"],
            description=generated["description"],
            category=template.category,
            duration=generated["duration"],
            difficulty=template.difficulty,
            language=language,
            is_ai_generated=generated["is_ai_generated"],
            user_goal=goal
        )
        
        db.session.add(new_card)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "card": new_card.to_dict()
        })
        
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# Получить все шаблоны
@app.route("/api/templates", methods=["GET"])
def get_templates():
    language = request.args.get("language", "RU")
    templates = CardTemplate.query.filter_by(language=language).all()
    
    return jsonify({
        "success": True,
        "templates": [t.to_dict() for t in templates]
    })

# Получить историю генераций
@app.route("/api/history", methods=["GET"])
def get_history():
    limit = request.args.get("limit", 50, type=int)
    cards = GeneratedCard.query.order_by(GeneratedCard.created_at.desc()).limit(limit).all()
    
    return jsonify({
        "success": True,
        "cards": [c.to_dict() for c in cards]
    })

# -------------------------------------------------------------
#                    RUN SERVER
# -------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"✅ Server starting on port {port}")
    print(f"✅ Database: {'PostgreSQL' if DATABASE_URL else 'SQLite'}")
    app.run(host="0.0.0.0", port=port, debug=False)
