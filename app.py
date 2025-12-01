# app.py
import os
import json
import re
from flask import Flask, request, jsonify
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise Exception("OPENAI_API_KEY not found!")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)


# ============================================================
#                   JSON-SAFE PARSER
# ============================================================
def extract_json(text: str):
    """
    Забирает первый корректный JSON из ответа модели.
    Работает даже если вокруг текст, эмодзи, переносы, пояснения.
    """
    # 1) Находим блок {...}
    matches = re.findall(r"\{.*?\}", text, re.DOTALL)
    for m in matches:
        try:
            return json.loads(m)
        except:
            continue
    return None


# ============================================================
#                        API ENDPOINT
# ============================================================
@app.route("/generate", methods=["POST"])
def generate():
    data = request.json

    action_type = data.get("actionType")
    goal = data.get("goal")
    energy = data.get("energy")
    engagement = data.get("engagement")
    session_type = data.get("sessionType")
    base_meaning = data.get("baseMeaning")
    language = data.get("language", "RU")

    lang_instruction = (
        "Пиши текст строго на русском языке."
        if language.upper() == "RU"
        else "Write text strictly in English."
    )

    prompt = f"""
Ты пишешь короткие тексты для приложения о здоровье.
{lang_instruction}

Входные данные:
- Тип действия: {action_type}
- Цель пользователя: {goal}
- Энергия: {energy}
- Вовлечение: {engagement}
- Спец-режим: {session_type}
- Базовый смысл: {base_meaning}

Верни СТРОГО JSON:
{{
  "title": "...",
  "description": "..."
}}
"""

    # ============================================================
    #                       Запрос к OpenAI
    # ============================================================
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты генератор коротких структурированных текстов. Всегда возвращай JSON."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0.7
        )

        raw = completion.choices[0].message["content"]
        print("RAW OPENAI RESPONSE:", raw)

        # ============================================================
        #                      Парсим JSON
        # ============================================================
        obj = extract_json(raw)
        if obj:
            return jsonify(obj)

        # fallback
        return jsonify({
            "title": base_meaning[:40],
            "description": base_meaning or "Сделай небольшой шаг."
        })

    except Exception as e:
        print("OPENAI ERROR:", e)
        return jsonify({
            "title": base_meaning[:40],
            "description": base_meaning or "Сделай небольшой шаг."
        })


@app.route("/")
def root():
    return {"status": "habit-ai-server running"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
