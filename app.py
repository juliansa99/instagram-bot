import os
import sqlite3
import requests
import cloudinary
import cloudinary.uploader
from flask import Flask, request, jsonify, render_template
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
IG_ACCESS_TOKEN    = os.environ.get("IG_ACCESS_TOKEN")
IG_ACCOUNT_ID      = os.environ.get("IG_ACCOUNT_ID")
CLOUDINARY_URL     = os.environ.get("CLOUDINARY_URL")

cloudinary.config(cloudinary_url=CLOUDINARY_URL)

def init_db():
    with sqlite3.connect("queue.db") as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                image_url    TEXT NOT NULL,
                caption      TEXT NOT NULL,
                status       TEXT DEFAULT 'pending',
                created_at   TEXT DEFAULT (datetime('now')),
                published_at TEXT
            )
        """)
        con.commit()

init_db()

def get_db():
    con = sqlite3.connect("queue.db")
    con.row_factory = sqlite3.Row
    return con

def generate_caption(image_base64: str, media_type: str) -> str:
    res = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "google/gemini-2.0-flash-001",
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{image_base64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": """Sos experto en marketing de productos capilares para el mercado argentino.
Analizá esta imagen de un producto capilar y escribí un pie de foto para Instagram.
Reglas:
- Español rioplatense (Argentina)
- Empezá con una frase gancho llamativa (máx 2 líneas)
- Describí el producto y sus beneficios con entusiasmo
- Incluí un call to action (ej: "Escribinos por DM", "Link en bio", "Consultá disponibilidad")
- Terminá con 10-15 hashtags capilares relevantes para Argentina
- Longitud total: 150-250 palabras
- Usá entre 3 y 5 emojis
Respondé SOLO con el pie de foto. Sin comillas, sin explicaciones."""
                    }
                ]
            }],
            "max_tokens": 600
        }
    )
    data = res.json()
    if "choices" not in data:
        raise Exception(f"Error OpenRouter: {data}")
    return data["choices"][0]["message"]["content"].strip()

def publish_to_instagram(image_url: str, caption: str) -> dict:
    container_res = requests.post(
        f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media",
        json={"image_url": image_url, "caption": caption, "access_token": IG_ACCESS_TOKEN}
    )
    container_data = container_res.json()
    if "id" not in container_data:
        raise Exception(f"Error creando contenedor: {container_data}")
    publish_res = requests.post(
        f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media_publish",
        json={"creation_id": container_data["id"], "access_token": IG_ACCESS_TOKEN}
    )
    publish_data = publish_res.json()
    if "id" not in publish_data:
        raise Exception(f"Error publicando: {publish_data}")
    return publish_data

def publish_next_post():
    con = get_db()
    try:
        post = con.execute(
            "SELECT * FROM posts WHERE status='pending' ORDER BY id ASC LIMIT 1"
        ).fetchone()
        if not post:
            return
        result = publish_to_instagram(post["image_url"], post["caption"])
        con.execute(
            "UPDATE posts SET status='published', published_at=datetime('now') WHERE id=?",
            (post["id"],)
        )
        con.commit()
    except Exception as e:
        logger.error(f"Error: {e}")
        if "post" in locals():
            con.execute("UPDATE posts SET status='error' WHERE id=?", (post["id"],))
            con.commit()
    finally:
        con.close()

scheduler = BackgroundScheduler()
scheduler.add_job(publish_next_post, "interval", hours=4, id="ig_publisher")
scheduler.start()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/upload", methods=["POST"])
def upload():
    try:
        data = request.json
        image_b64  = data["image"]
        media_type = data["media_type"]
        upload_result = cloudinary.uploader.upload(
            f"data:{media_type};base64,{image_b64}",
            folder="instagram-bot"
        )
        image_url = upload_result["secure_url"]
        caption   = generate_caption(image_b64, media_type)
        con = get_db()
        cur = con.execute(
            "INSERT INTO posts (image_url, caption) VALUES (?, ?)",
            (image_url, caption)
        )
        post_id = cur.lastrowid
        con.commit()
        con.close()
        return jsonify({"ok": True, "id": post_id, "image_url": image_url, "caption": caption})
    except Exception as e:
        logger.error(f"Error en upload: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/queue")
def get_queue():
    con = get_db()
    posts = con.execute("SELECT * FROM posts ORDER BY id ASC").fetchall()
    con.close()
    return jsonify([dict(p) for p in posts])

@app.route("/api/post/<int:post_id>", methods=["PUT"])
def update_post(post_id):
    data = request.json
    con = get_db()
    con.execute("UPDATE posts SET caption=? WHERE id=? AND status='pending'", (data["caption"], post_id))
    con.commit()
    con.close()
    return jsonify({"ok": True})

@app.route("/api/post/<int:post_id>", methods=["DELETE"])
def delete_post(post_id):
    con = get_db()
    con.execute("DELETE FROM posts WHERE id=? AND status='pending'", (post_id,))
    con.commit()
    con.close()
    return jsonify({"ok": True})

@app.route("/api/publish-now/<int:post_id>", methods=["POST"])
def publish_now(post_id):
    con = get_db()
    try:
        post = con.execute("SELECT * FROM posts WHERE id=? AND status='pending'", (post_id,)).fetchone()
        if not post:
            return jsonify({"ok": False, "error": "Post no encontrado"}), 404
        result = publish_to_instagram(post["image_url"], post["caption"])
        con.execute("UPDATE posts SET status='published', published_at=datetime('now') WHERE id=?", (post_id,))
        con.commit()
        return jsonify({"ok": True, "ig_id": result["id"]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        con.close()

@app.route("/api/next-publish")
def next_publish():
    job = scheduler.get_job("ig_publisher")
    if job and job.next_run_time:
        return jsonify({"next": job.next_run_time.isoformat()})
    return jsonify({"next": None})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
