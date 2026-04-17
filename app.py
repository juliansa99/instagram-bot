import os
import json
import time
import base64
import sqlite3
import requests
import anthropic
import cloudinary
import cloudinary.uploader
from flask import Flask, request, jsonify, render_template
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ─── CONFIGURACIÓN (viene de variables de entorno) ───────────────────────────
ANTHROPIC_API_KEY   = os.environ.get("ANTHROPIC_API_KEY")
IG_ACCESS_TOKEN     = os.environ.get("IG_ACCESS_TOKEN")
IG_ACCOUNT_ID       = os.environ.get("IG_ACCOUNT_ID")
CLOUDINARY_URL      = os.environ.get("CLOUDINARY_URL")

cloudinary.config(cloudinary_url=CLOUDINARY_URL)

# ─── BASE DE DATOS (cola de posts) ───────────────────────────────────────────
def init_db():
    with sqlite3.connect("queue.db") as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                image_url   TEXT NOT NULL,
                caption     TEXT NOT NULL,
                status      TEXT DEFAULT 'pending',
                created_at  TEXT DEFAULT (datetime('now')),
                published_at TEXT
            )
        """)
        con.commit()

init_db()

def get_db():
    con = sqlite3.connect("queue.db")
    con.row_factory = sqlite3.Row
    return con

# ─── IA: generar caption con Claude ──────────────────────────────────────────
def generate_caption(image_base64: str, media_type: str) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=600,
        system="""Sos experto en marketing de productos capilares para el mercado argentino.
Creás pies de foto para Instagram que venden y generan engagement.
Reglas:
- Español rioplatense (Argentina)
- Empezá con una frase gancho (máx 2 líneas)
- Describí el producto y sus beneficios con entusiasmo
- Incluí un call to action (ej: "Escribinos por DM", "Link en bio", "Consultá disponibilidad")
- Terminá con 10-15 hashtags capilares relevantes para Argentina
- Longitud: 150-250 palabras
- Usá entre 3 y 5 emojis
Respondé SOLO con el pie de foto. Sin comillas, sin explicaciones.""",
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_base64,
                    }
                },
                {
                    "type": "text",
                    "text": "Analizá esta imagen de producto capilar y escribí el pie de foto para Instagram."
                }
            ]
        }]
    )
    return msg.content[0].text.strip()

# ─── INSTAGRAM: publicar un post ─────────────────────────────────────────────
def publish_to_instagram(image_url: str, caption: str) -> dict:
    # Paso 1: crear contenedor de media
    container_res = requests.post(
        f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media",
        json={
            "image_url": image_url,
            "caption": caption,
            "access_token": IG_ACCESS_TOKEN
        }
    )
    container_data = container_res.json()
    if "id" not in container_data:
        raise Exception(f"Error creando contenedor: {container_data}")

    # Paso 2: publicar el contenedor
    publish_res = requests.post(
        f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media_publish",
        json={
            "creation_id": container_data["id"],
            "access_token": IG_ACCESS_TOKEN
        }
    )
    publish_data = publish_res.json()
    if "id" not in publish_data:
        raise Exception(f"Error publicando: {publish_data}")

    return publish_data

# ─── SCHEDULER: publica el próximo post de la cola cada 4 horas ──────────────
def publish_next_post():
    logger.info(f"[{datetime.now()}] Revisando cola...")
    con = get_db()
    try:
        post = con.execute(
            "SELECT * FROM posts WHERE status='pending' ORDER BY id ASC LIMIT 1"
        ).fetchone()

        if not post:
            logger.info("Cola vacía, nada que publicar.")
            return

        logger.info(f"Publicando post #{post['id']}...")
        result = publish_to_instagram(post["image_url"], post["caption"])
        con.execute(
            "UPDATE posts SET status='published', published_at=datetime('now') WHERE id=?",
            (post["id"],)
        )
        con.commit()
        logger.info(f"Post #{post['id']} publicado. IG ID: {result['id']}")

    except Exception as e:
        logger.error(f"Error publicando: {e}")
        if "post" in locals():
            con.execute("UPDATE posts SET status='error' WHERE id=?", (post["id"],))
            con.commit()
    finally:
        con.close()

scheduler = BackgroundScheduler()
scheduler.add_job(publish_next_post, "interval", hours=4, id="ig_publisher")
scheduler.start()

# ─── RUTAS WEB ────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/upload", methods=["POST"])
def upload():
    """Recibe imagen, genera caption con IA y la agrega a la cola."""
    try:
        data = request.json
        image_b64  = data["image"]        # base64 sin el prefijo data:...
        media_type = data["media_type"]   # image/jpeg o image/png

        # 1. Subir imagen a Cloudinary para obtener URL pública
        upload_result = cloudinary.uploader.upload(
            f"data:{media_type};base64,{image_b64}",
            folder="instagram-bot"
        )
        image_url = upload_result["secure_url"]

        # 2. Generar caption con Claude
        caption = generate_caption(image_b64, media_type)

        # 3. Agregar a la cola
        con = get_db()
        cur = con.execute(
            "INSERT INTO posts (image_url, caption) VALUES (?, ?)",
            (image_url, caption)
        )
        post_id = cur.lastrowid
        con.commit()
        con.close()

        return jsonify({
            "ok": True,
            "id": post_id,
            "image_url": image_url,
            "caption": caption
        })

    except Exception as e:
        logger.error(f"Error en upload: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/queue", methods=["GET"])
def get_queue():
    """Devuelve todos los posts en la cola."""
    con = get_db()
    posts = con.execute(
        "SELECT * FROM posts ORDER BY id ASC"
    ).fetchall()
    con.close()
    return jsonify([dict(p) for p in posts])

@app.route("/api/post/<int:post_id>", methods=["PUT"])
def update_post(post_id):
    """Edita el caption de un post pendiente."""
    data = request.json
    con = get_db()
    con.execute(
        "UPDATE posts SET caption=? WHERE id=? AND status='pending'",
        (data["caption"], post_id)
    )
    con.commit()
    con.close()
    return jsonify({"ok": True})

@app.route("/api/post/<int:post_id>", methods=["DELETE"])
def delete_post(post_id):
    """Elimina un post pendiente de la cola."""
    con = get_db()
    con.execute("DELETE FROM posts WHERE id=? AND status='pending'", (post_id,))
    con.commit()
    con.close()
    return jsonify({"ok": True})

@app.route("/api/publish-now/<int:post_id>", methods=["POST"])
def publish_now(post_id):
    """Publica un post inmediatamente (sin esperar el scheduler)."""
    con = get_db()
    try:
        post = con.execute(
            "SELECT * FROM posts WHERE id=? AND status='pending'", (post_id,)
        ).fetchone()
        if not post:
            return jsonify({"ok": False, "error": "Post no encontrado o ya publicado"}), 404
        result = publish_to_instagram(post["image_url"], post["caption"])
        con.execute(
            "UPDATE posts SET status='published', published_at=datetime('now') WHERE id=?",
            (post_id,)
        )
        con.commit()
        return jsonify({"ok": True, "ig_id": result["id"]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        con.close()

@app.route("/api/next-publish", methods=["GET"])
def next_publish():
    """Dice cuándo será la próxima publicación."""
    job = scheduler.get_job("ig_publisher")
    if job and job.next_run_time:
        return jsonify({"next": job.next_run_time.isoformat()})
    return jsonify({"next": None})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
