# app.py - РАБОТАЕТ С POSTGRESQL
import os
import json
import re
import random
import psycopg2
from psycopg2 import pool
from flask import Flask, request, jsonify
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
CORS(app)

# -------------------------------------------------------------
#                    DATABASE CONNECTION
# -------------------------------------------------------------
DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    raise Exception("DATABASE_URL not found in environment variables!")

print(f"✅ Database URL configured: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'Connected'}")

# Создаем пул подключений
connection_pool = None

def init_db_pool():
    """Инициализировать пул подключений к PostgreSQL"""
    global connection_pool
    try:
        # Конвертируем URL если нужно
        db_url = DATABASE_URL
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)
        
        connection_pool = psycopg2.pool.SimpleConnectionPool(
            1,  # минимальное количество соединений
            10, # максимальное количество соединений
            db_url
        )
        print("✅ PostgreSQL connection pool created")
        
        # Инициализируем таблицы
        init_tables()
        
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        raise

def get_connection():
    """Получить соединение из пула"""
    if not connection_pool:
        init_db_pool()
    return connection_pool.getconn()

def return_connection(conn):
    """Вернуть соединение в пул"""
    if connection_pool:
        connection_pool.putconn(conn)

def init_tables():
    """Инициализировать таблицы в БД"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # Таблица шаблонов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS card_templates (
                id SERIAL PRIMARY KEY,
                category VARCHAR(100) NOT NULL,
                base_text TEXT NOT NULL,
                difficulty VARCHAR(50) DEFAULT 'легко',
                duration INTEGER DEFAULT 300,
                tags TEXT DEFAULT '',
                language VARCHAR(10) DEFAULT 'RU',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица сгенерированных карточек
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS generated_cards (
                id SERIAL PRIMARY KEY,
                template_id INTEGER NOT NULL,
                title VARCHAR(200) NOT NULL,
                description TEXT NOT NULL,
                category VARCHAR(100) NOT NULL,
                duration INTEGER NOT NULL,
                difficulty VARCHAR(50) NOT NULL,
                language VARCHAR(10) DEFAULT 'RU',
                is_ai_generated BOOLEAN DEFAULT TRUE,
                user_goal VARCHAR(200),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Проверяем, есть ли демо-шаблоны
        cursor.execute("SELECT COUNT(*) FROM card_templates")
        count = cursor.fetchone()[0]
        
        if count == 0:
            # Добавляем демо-шаблоны
            demo_templates = [
                ("дыхание", "Сделай {N} глубоких вдохов через нос и медленных выдохов через рот", "легко", 120, "релакс,офис,стресс", "RU"),
                ("шея_плечи", "Повращай плечами {N} раз вперед и {N} раз назад", "легко", 180, "разминка,офис,сидячая работа", "RU"),
                ("осанка", "Выпрями спину и удерживай правильную осанку {N} минут", "средне", 300, "осанка,работа,здоровье спины", "RU"),
                ("глаза", "Отведи взгляд от экрана и сфокусируйся на удаленном объекте {N} секунд", "легко", 60, "зрение,отдых,экран", "RU"),
                ("ноги", "Встань и потянись, подняв руки вверх на {N} секунд", "легко", 90, "разминка,перерыв,кровообращение", "RU"),
                ("breathing", "Take {N} deep breaths through your nose and slow exhales through your mouth", "easy", 120, "relax,office,stress", "EN"),
                ("neck_shoulders", "Rotate your shoulders {N} times forward and {N} times backward", "easy", 180, "warmup,office,sitting", "EN")
            ]
            
            cursor.executemany("""
                INSERT INTO card_templates (category, base_text, difficulty, duration, tags, language)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, demo_templates)
            
            print(f"✅ Added {len(demo_templates)} demo templates to PostgreSQL")
        else:
            print(f"✅ Database already has {count} templates")
        
        conn.commit()
        cursor.close()
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error initializing tables: {e}")
        raise
    finally:
        return_connection(conn)

# -------------------------------------------------------------
#                    DATABASE FUNCTIONS
# -------------------------------------------------------------
def get_random_template(language="RU"):
    """Получить случайный шаблон из БД"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM card_templates 
            WHERE language = %s 
            ORDER BY RANDOM() 
            LIMIT 1
        """, (language,))
        
        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            template = dict(zip(columns, row))
            cursor.close()
            return template
        return None
        
    except Exception as e:
        print(f"❌ Error getting template: {e}")
        return None
    finally:
        return_connection(conn)

def save_generated_card(card_data):
    """Сохранить сгенерированную карточку в БД"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO generated_cards 
            (template_id, title, description, category, duration, difficulty, language, is_ai_generated, user_goal)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            card_data['template_id'],
            card_data['title'],
            card_data['description'],
            card_data['category'],
            card_data['duration'],
            card_data['difficulty'],
            card_data['language'],
            card_data['is_ai_generated'],
            card_data['user_goal']
        ))
        
        card_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        return card_id
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error saving card: {e}")
        raise
    finally:
        return_connection(conn)

def get_templates(language="RU"):
    """Получить все шаблоны"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM card_templates WHERE language = %s",
            (language,)
        )
        
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        templates = [dict(zip(columns, row)) for row in rows]
        
        cursor.close()
        return templates
        
    except Exception as e:
        print(f"❌ Error getting templates: {e}")
        return []
    finally:
        return_connection(conn)

def get_generated_cards(limit=20):
    """Получить историю генераций"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM generated_cards 
            ORDER BY created_at DESC 
            LIMIT %s
        """, (limit,))
        
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        cards = [dict(zip(columns, row)) for row in rows]
        
        cursor.close()
        return cards
        
    except Exception as e:
        print(f"❌ Error getting history: {e}")
        return []
    finally:
        return_connection(conn)

def get_stats():
    """Получить статистику БД"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM card_templates")
        templates_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM generated_cards")
        generated_count = cursor.fetchone()[0]
        
        cursor.close()
        return templates_count, generated_count
        
    except Exception as e:
        print(f"❌ Error getting stats: {e}")
        return 0, 0
    finally:
        return_connection(conn)

# -------------------------------------------------------------
#                    OPENAI FUNCTIONS
# -------------------------------------------------------------
def generate_with_openai(template, goal, language):
    """Генерирует вариацию через OpenAI"""
    
    lang_text = "русском" if language == "RU" else "английском"
    n_value = random.randint(3, 10)
    
    prompt = f"""
Напиши на {lang_text} языке.

Шаблон упражнения: "{template['base_text']}"
Категория: {template['category']}
Длительность: {template['duration']} секунд

Цель пользователя: {goal}

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
                "title": data.get("title", template['category']),
                "description": data.get("description", template['base_text'].replace("{N}", str(n_value))),
                "duration": data.get("duration", template['duration']),
                "is_ai_generated": True
            }
            
    except Exception as e:
        print(f"OpenAI error: {e}")
    
    # Fallback
    return {
        "title": template['category'],
        "description": template['base_text'].replace("{N}", str(random.randint(3, 10))),
        "duration": template['duration'],
        "is_ai_generated": False
    }

# -------------------------------------------------------------
#                    API ENDPOINTS
# -------------------------------------------------------------

@app.route("/")
def health():
    """Health check endpoint"""
    try:
        templates_count, generated_count = get_stats()
        return jsonify({
            "status": "🚀 Server is running",
            "database": "PostgreSQL",
            "templates": templates_count,
            "generated_cards": generated_count,
            "database_connected": True,
            "endpoints": {
                "POST /api/generate": "Generate new card",
                "GET /api/templates": "Get all templates",
                "GET /api/history": "Get generation history",
                "POST /generate": "Legacy OpenAI endpoint"
            }
        })
    except Exception as e:
        return jsonify({
            "status": "⚠️ Server running (database error)",
            "error": str(e),
            "database_connected": False
        })

# Основной endpoint для Android
@app.route("/api/generate", methods=["POST"])
def generate_card():
    try:
        data = request.json
        goal = data.get("goal", "Улучшить здоровье")
        language = data.get("language", "RU")
        
        # Получаем случайный шаблон из БД
        template = get_random_template(language)
        if not template:
            return jsonify({
                "success": False,
                "error": f"No templates found for language: {language}"
            }), 404
        
        # Генерируем через OpenAI
        generated = generate_with_openai(template, goal, language)
        
        # Подготовка данных для сохранения
        card_data = {
            "template_id": template['id'],
            "title": generated["title"],
            "description": generated["description"],
            "category": template['category'],
            "duration": generated["duration"],
            "difficulty": template['difficulty'],
            "language": language,
            "is_ai_generated": generated["is_ai_generated"],
            "user_goal": goal
        }
        
        # Сохраняем в БД
        card_id = save_generated_card(card_data)
        
        # Формируем ответ
        response_card = {
            "id": card_id,
            **card_data,
            "created_at": datetime.utcnow().isoformat()
        }
        
        return jsonify({
            "success": True,
            "card": response_card
        })
        
    except Exception as e:
        print(f"❌ Error in /api/generate: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to generate card",
            "message": str(e)
        }), 500

# Получить все шаблоны
@app.route("/api/templates", methods=["GET"])
def api_get_templates():
    language = request.args.get("language", "RU")
    templates = get_templates(language)
    
    return jsonify({
        "success": True,
        "templates": templates
    })

# Получить историю генераций
@app.route("/api/history", methods=["GET"])
def api_get_history():
    limit = request.args.get("limit", 20, type=int)
    cards = get_generated_cards(limit)
    
    return jsonify({
        "success": True,
        "cards": cards
    })

# Legacy endpoint для совместимости
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
#                    STARTUP
# -------------------------------------------------------------
# Инициализируем БД при импорте
try:
    init_db_pool()
    print("✅ Database initialized successfully")
except Exception as e:
    print(f"⚠️ Database initialization failed: {e}")
    print("⚠️ Server will start without database")

# -------------------------------------------------------------
#                    RUN SERVER
# -------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"✅ Starting server on port {port}")
    print(f"✅ Using PostgreSQL with psycopg2")
    app.run(host="0.0.0.0", port=port, debug=False)
