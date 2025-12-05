# app.py - РАБОТАЕТ БЕЗ ПРОБЛЕМ
import os
import json
import re
import random
import sqlite3
import requests
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
#                    SQLITE DATABASE (Локальная БД)
# -------------------------------------------------------------
SQLITE_DB = "cards.db"

def init_sqlite():
    """Инициализировать SQLite базу"""
    conn = sqlite3.connect(SQLITE_DB)
    cursor = conn.cursor()
    
    # Таблица шаблонов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS card_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            base_text TEXT NOT NULL,
            difficulty TEXT DEFAULT 'легко',
            duration INTEGER DEFAULT 300,
            tags TEXT DEFAULT '',
            language TEXT DEFAULT 'RU',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Таблица сгенерированных карточек
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS generated_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            duration INTEGER NOT NULL,
            difficulty TEXT NOT NULL,
            language TEXT DEFAULT 'RU',
            is_ai_generated BOOLEAN DEFAULT 1,
            user_goal TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Проверяем, есть ли демо-шаблоны
    cursor.execute("SELECT COUNT(*) FROM card_templates")
    count = cursor.fetchone()[0]
    
    if count == 0:
        # Добавляем демо-шаблоны
        templates = [
            ("дыхание", "Сделай {N} глубоких вдохов через нос и медленных выдохов через рот", "легко", 120, "релакс,офис,стресс", "RU"),
            ("шея_плечи", "Повращай плечами {N} раз вперед и {N} раз назад", "легко", 180, "разминка,офис,сидячая работа", "RU"),
            ("осанка", "Выпрями спину и удерживай правильную осанку {N} минут", "средне", 300, "осанка,работа,здоровье спины", "RU"),
            ("глаза", "Отведи взгляд от экрана и сфокусируйся на удаленном объекте {N} секунд", "легко", 60, "зрение,отдых,экран", "RU"),
            ("ноги", "Встань и потянись, подняв руки вверх на {N} секунд", "легко", 90, "разминка,перерыв,кровообращение", "RU")
        ]
        
        cursor.executemany("""
            INSERT INTO card_templates (category, base_text, difficulty, duration, tags, language)
            VALUES (?, ?, ?, ?, ?, ?)
        """, templates)
        
        print(f"✅ Added {len(templates)} templates to SQLite")
    
    conn.commit()
    conn.close()
    print("✅ SQLite database initialized")

# Инициализируем SQLite
init_sqlite()

# -------------------------------------------------------------
#                    SQLITE FUNCTIONS
# -------------------------------------------------------------
def get_sqlite_connection():
    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row
    return conn

def get_random_template(language="RU"):
    """Получить случайный шаблон из SQLite"""
    conn = get_sqlite_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM card_templates 
        WHERE language = ? 
        ORDER BY RANDOM() 
        LIMIT 1
    """, (language,))
    
    row = cursor.fetchone()
    conn.close()
    
    return dict(row) if row else None

def save_generated_card(card_data):
    """Сохранить карточку в SQLite"""
    conn = get_sqlite_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO generated_cards 
        (template_id, title, description, category, duration, difficulty, language, is_ai_generated, user_goal)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    
    card_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return card_id

def get_templates(language="RU"):
    """Получить все шаблоны из SQLite"""
    conn = get_sqlite_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM card_templates WHERE language = ?", (language,))
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def get_stats():
    """Получить статистику из SQLite"""
    conn = get_sqlite_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM card_templates")
    templates_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM generated_cards")
    generated_count = cursor.fetchone()[0]
    
    conn.close()
    return templates_count, generated_count

# -------------------------------------------------------------
#                    RAILWAY POSTGRESQL через REST API
# -------------------------------------------------------------
def sync_to_postgresql(card_data):
    """Синхронизировать карточку с Railway PostgreSQL через REST"""
    try:
        railway_token = os.getenv("RAILWAY_TOKEN")
        database_id = os.getenv("RAILWAY_DATABASE_ID")
        
        if not railway_token or not database_id:
            return False  # Пропускаем если нет токена
        
        # Railway GraphQL API для выполнения SQL
        url = "https://backboard.railway.app/graphql/v2"
        headers = {
            "Authorization": f"Bearer {railway_token}",
            "Content-Type": "application/json"
        }
        
        # SQL запрос для вставки
        sql = f"""
        INSERT INTO generated_cards 
        (template_id, title, description, category, duration, difficulty, language, is_ai_generated, user_goal, created_at)
        VALUES (
            {card_data['template_id']}, 
            '{card_data['title'].replace("'", "''")}', 
            '{card_data['description'].replace("'", "''")}', 
            '{card_data['category']}', 
            {card_data['duration']}, 
            '{card_data['difficulty']}', 
            '{card_data['language']}', 
            {card_data['is_ai_generated']}, 
            '{card_data['user_goal'].replace("'", "''")}', 
            NOW()
        )
        """
        
        payload = {
            "query": """
                mutation($input: ExecuteSQLInput!) {
                    executeSQL(input: $input) {
                        data
                    }
                }
            """,
            "variables": {
                "input": {
                    "databaseId": database_id,
                    "query": sql
                }
            }
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            print("✅ Synced card to Railway PostgreSQL")
            return True
        else:
            print(f"❌ Sync failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ PostgreSQL sync error: {e}")
        return False

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
            "database": "SQLite (with PostgreSQL sync)",
            "templates": templates_count,
            "generated_cards": generated_count,
            "postgresql_sync": bool(os.getenv("RAILWAY_TOKEN")),
            "endpoints": {
                "POST /api/generate": "Generate new card",
                "GET /api/templates": "Get all templates",
                "GET /api/history": "Get generation history"
            }
        })
    except Exception as e:
        return jsonify({
            "status": "⚠️ Server running",
            "error": str(e)
        })

# Основной endpoint для Android
@app.route("/api/generate", methods=["POST"])
def generate_card():
    try:
        data = request.json
        goal = data.get("goal", "Улучшить здоровье")
        language = data.get("language", "RU")
        
        # Получаем случайный шаблон из SQLite
        template = get_random_template(language)
        if not template:
            # Если нет шаблонов, создаем простую карточку
            return jsonify({
                "success": True,
                "card": {
                    "id": random.randint(1000, 9999),
                    "template_id": 0,
                    "title": "Упражнение",
                    "description": f"Помни о своей цели: {goal}",
                    "category": "общее",
                    "duration": 300,
                    "difficulty": "легко",
                    "language": language,
                    "is_ai_generated": False,
                    "user_goal": goal,
                    "created_at": datetime.utcnow().isoformat()
                }
            })
        
        # Генерируем через OpenAI
        generated = generate_with_openai(template, goal, language)
        
        # Подготовка данных
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
        
        # Сохраняем в SQLite
        card_id = save_generated_card(card_data)
        
        # Синхронизируем с PostgreSQL (если настроено)
        sync_to_postgresql(card_data)
        
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
        print(f"❌ Error: {e}")
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
#                    RUN SERVER
# -------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"✅ Starting server on port {port}")
    print(f"✅ Database: SQLite (cards.db)")
    print(f"✅ OpenAI: {'Ready' if API_KEY else 'Not configured'}")
    app.run(host="0.0.0.0", port=port, debug=False)
