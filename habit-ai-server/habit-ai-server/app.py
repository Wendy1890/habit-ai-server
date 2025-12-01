# app.py
import os
from flask import Flask, request, jsonify
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise Exception("OPENAI_API_KEY not found!")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)

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
        "Пиши текст только на русском языке." if language == "RU"
        else "Write text only in English."
    )

    prompt = f"""
Ты пишешь короткие тексты для приложения о здоровье.
{lang_instruction}

Дано:
- Тип действия: {action_type}
- Цель пользователя: {goal}
- Энергия: {energy}
- Вовлечение: {engagement}
- Спец-режим: {session_type}
- Базовый смысл: {base_meaning}

Верни JSON строго вида:
{{"title": "...", "description": "..."}}
"""

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты генератор коротких текстов."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=120,
            temperature=0.8
        )

        text = completion.choices[0].message["content"]

        import json
        try:
            obj = json.loads(text)
            return jsonify(obj)
        except:
            return jsonify({
                "title": base_meaning[:40],
                "description": base_meaning or "Сделай небольшой шаг."
            })

    except:
        return jsonify({
            "title": base_meaning[:40],
            "description": base_meaning or "Сделай небольшой шаг."
        })

@app.route("/")
def root():
    return {"status": "habit-ai-server running"}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
