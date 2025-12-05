# app.py - с asyncpg для PostgreSQL
import os
import json
import re
import random
import asyncio
import asyncpg
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import openai
from datetime import datetime
from contextlib import asynccontextmanager

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

# PostgreSQL connection string от Railway
DATABASE_URL = os.getenv('DATABASE_URL')
print(f"✅ PostgreSQL URL: {DATABASE_URL.split('@')[1] if DATABASE_URL and '@' in DATABASE_URL else 'Configured'}")

# -------------------------------------------------------------
#                    DATABASE POOL
# -------------------------------------------------------------
pool = None

async def create_db_pool():
    """Создать пул подключений к PostgreSQL"""
    global pool
    try:
        pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=10,
            command_timeout=60
        )
        print("✅ PostgreSQL connection pool created")
        await init_tables()
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        raise

async def init_tables():
    """Инициализировать таблицы в БД"""
    async with pool.acquire() as conn:
        # Таблица шаблонов
        await conn.execute("""
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
        await conn.execute("""
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
        count = await conn.fetchval("SELECT COUNT(*) FROM card_templates")
        
        if count == 0:
            # Добавляем демо-шаблоны
            templates = [
                ("дыхание", "Сделай {N} глубоких вдохов через нос и медленных выдохов через рот", "легко", 120, "релакс,офис,стресс", "RU"),
                ("шея_плечи", "Повращай плечами {N} раз вперед и {N} раз назад", "легко", 180, "разминка,офис,сидячая работа", "RU"),
                ("осанка", "Выпрями спину и удерживай правильную осанку {N} минут", "средне", 300, "осанка,работа,здоровье спины", "RU"),
                ("глаза", "Отведи взгляд от экрана и сфокусируйся на удаленном объекте {N} секунд", "легко", 60, "зрение,отдых,экран", "RU"),
                ("ноги", "Встань и потянись, подняв руки вверх на {N} секунд", "легко", 90, "разминка,перерыв,кровообращение", "RU"),
                ("breathing", "Take {N} deep breaths through your nose and slow exhales through your mouth", "easy", 120, "relax,office,stress", "EN"),
                ("neck_shoulders", "Rotate your shoulders {N} times forward and {N} times backward", "easy", 180, "warmup,office,sitting", "EN")
            ]
            
            for template in templates:
                await conn.execute("""
                    INSERT INTO card_templates (category, base_text, difficulty, duration, tags, language)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """, *template)
            
            print(f"✅ Added {len(templates)} demo templates to PostgreSQL")
        else:
            print(f"✅ Database already has {count} templates")

# -------------------------------------------------------------
#                    DATABASE FUNCTIONS (async)
# -------------------------------------------------------------
@asynccontextmanager
async def get_connection():
    """Контекстный менеджер для подключения к БД"""
    conn = await pool.acquire()
    try:
        yield conn
    finally:
        await pool.release(conn)

async def get_random_template(language="RU"):
    """Получить случайный шаблон из БД"""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM card_templates WHERE language = $1 ORDER BY RANDOM() LIMIT 1",
            language
        )
        return dict(row) if row else None

async def save_generated_card(card_data):
    """Сохранить сгенерированную карточку в БД"""
    async with get_connection() as conn:
        card_id = await conn.fetchval("""
            INSERT INTO generated_cards 
            (template_id, title, description, category, duration, difficulty, language, is_ai_generated, user_goal)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
        """, 
            card_data['template_id'],
            card_data['title'],
            card_data['description'],
            card_data['category'],
            card_data['duration'],
            card_data['difficulty'],
            card_data['language'],
            card_data['is_ai_generated'],
            card_data['user_goal']
        )
        return card_id

async def get_templates(language="RU"):
    """Получить все шаблоны"""
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM card_templates WHERE language = $1",
            language
        )
        return [dict(row) for row in rows]

async def get_generated_cards(limit=20):
    """Получить историю генераций"""
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM generated_cards ORDER BY created_at DESC LIMIT $1",
            limit
        )
        return [dict(row) for row in rows]

async def get_stats():
    """Получить статистику БД"""
    async with get_connection() as conn:
        templates_count = await conn.fetchval("SELECT COUNT(*) FROM card_templates")
        generated_count = await conn.fetchval("SELECT COUNT(*) FROM generated_cards")
        return templates_count, generated_count

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
#                    SYNC WRAPPERS для Flask (Flask не async)
# -------------------------------------------------------------
def run_async(coro):
    """Запустить асинхронную функцию синхронно"""
    return asyncio.run(coro)

# Синхронные обертки для Flask endpoints
def sync_get_random_template(language="RU"):
    return run_async(get_random_template(language))

def sync_save_generated_card(card_data):
    return run_async(save_generated_card(card_data))

def sync_get_templates(language="RU"):
    return run_async(get_templates(language))

def sync_get_generated_cards(limit=20):
    return run_async(get_generated_cards(limit))

def sync_get_stats():
    return run_async(get_stats())

# -------------------------------------------------------------
#                    API ENDPOINTS
# -------------------------------------------------------------

@app.route("/")
def health():
    """Health check endpoint"""
    try:
        templates_count, generated_count = sync_get_stats()
        return jsonify({
            "status": "🚀 Server is running",
            "database": "PostgreSQL (asyncpg)",
            "templates": templates_count,
            "generated_cards": generated_count,
            "database_url_short": DATABASE_URL.split('@')[1] if DATABASE_URL and '@' in DATABASE_URL else "configured",
            "endpoints": {
                "POST /api/generate": "Generate new card",
                "GET /api/templates": "Get all templates",
                "GET /api/history": "Get generation history"
            }
        })
    except Exception as e:
        return jsonify({
            "status": "⚠️ Server error",
            "error": str(e),
            "database_url": DATABASE_URL[:50] + "..." if DATABASE_URL else "not configured"
        }), 500

# Основной endpoint для Android
@app.route("/api/generate", methods=["POST"])
def generate_card():
    try:
        data = request.json
        goal = data.get("goal", "Улучшить здоровье")
        language = data.get("language", "RU")
        
        # Получаем случайный шаблон из БД
        template = sync_get_random_template(language)
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
        card_id = sync_save_generated_card(card_data)
        
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
        print(f"Error in /api/generate: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to generate card",
            "message": str(e)
        }), 500

# Получить все шаблоны
@app.route("/api/templates", methods=["GET"])
def api_get_templates():
    language = request.args.get("language", "RU")
    templates = sync_get_templates(language)
    
    return jsonify({
        "success": True,
        "templates": templates
    })

# Получить историю генераций
@app.route("/api/history", methods=["GET"])
def api_get_history():
    limit = request.args.get("limit", 20, type=int)
    cards = sync_get_generated_cards(limit)
    
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
#                    STARTUP & SHUTDOWN
# -------------------------------------------------------------
@app.before_first_request
def startup():
    """Инициализация при старте сервера"""
    try:
        run_async(create_db_pool())
        print("✅ Server initialized successfully")
    except Exception as e:
        print(f"❌ Startup error: {e}")

@app.teardown_appcontext
def shutdown(exception=None):
    """Очистка при завершении"""
    if pool:
        run_async(pool.close())
        print("✅ Database pool closed")

# -------------------------------------------------------------
#                    RUN SERVER
# -------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"✅ Starting server on port {port}")
    print(f"✅ Using asyncpg for PostgreSQL")
    
    # Инициализируем пул при запуске
    try:
        run_async(create_db_pool())
    except Exception as e:
        print(f"⚠️ Could not connect to database: {e}")
        print("⚠️ Server will start without database connection")
    
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
