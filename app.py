# app.py
import os
import json
import re
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from openai import OpenAI

# -------------------------------------------------------------
#                    LOAD ENV
# -------------------------------------------------------------
load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise Exception("OPENAI_API_KEY not found!")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)


# -------------------------------------------------------------
#                  /generate — MAIN ENDPOINT
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
                model="gpt-5.1",
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
#                       HEALTH CHECK
# -------------------------------------------------------------
@app.route("/")
def root():
    return {"status": "habit-ai-server running"}


# -------------------------------------------------------------
#                       RUN LOCAL
# -------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
