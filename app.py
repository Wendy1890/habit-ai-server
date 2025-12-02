# app.py
import os
import json
import re
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from openai import OpenAI

# Загружаем .env
load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise Exception("OPENAI_API_KEY not found!")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)


# =============================================================
#                     /generate  — API метод
# =============================================================
@app.route("/generate", methods=["POST"])
def generate():
    try:
        data = request.json

        action_type = data.get("actionType")
        goal = data.get("goal")
        energy = data.get("energy")
        engagement = data.get("engagement")
        session_type = data.get("sessionType")
        base_meaning = data.get("baseMeaning")
        language = data.get("language", "RU")

        lang_instruction = (
            "Пиши текст только на русском языке."
            if language == "RU" else
            "Write text only in English."
        )

        prompt = f"""
Ты пишешь короткие тексты для приложения о здоровье и привычках.
{lang_instruction}

Дано:
- Тип действия: {action_type}
- Цель пользователя: {goal}
- Энергия: {energy}
- Вовлечённость: {engagement}
- Спец-режим: {session_type}
- Базовый смысл: {base_meaning}

Верни JSON строго формата:
{{"title": "...", "description": "..."}}
"""

        # ================= OpenAI запрос =================
        try:
    completion = client.chat.completions.create(
        model="gpt-5.1",
        messages=[
            {"role": "system", "content": "Ты генератор коротких текстов."},
            {"role": "user", "content": prompt}
        ],
        max_completion_tokens=150,
        temperature=0.8
    )

    raw = completion.choices[0].message.content

    import json, re
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            obj = json.loads(match.group(0))
            return jsonify(obj)
        except:
            pass

    return jsonify({
        "title": base_meaning[:40],
        "description": base_meaning or fallback
    })

except Exception as err:
    print("OPENAI ERROR:", err)
    return jsonify({
        "title": base_meaning[:40],
        "description": base_meaning or fallback
    })



# =============================================================
#                       health check
# =============================================================
@app.route("/")
def root():
    return {"status": "habit-ai-server running"}


# =============================================================
#                       RUN (локально)
# =============================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
