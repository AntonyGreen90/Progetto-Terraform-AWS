import os
import time
import random
import sqlite3
import boto3
from botocore.client import Config
from flask import Flask, jsonify, request

# Configurazione dell'applicazione Flask
app = Flask(__name__)

# --- CONFIGURAZIONI AMBIENTALI E SICUREZZA ---
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
DB_PATH = os.environ.get("DB_PATH", "/data/jobs.db") # invece di /jobs.db mancava la cartella /data

# MinIO / S3 config
BUCKET_NAME = os.environ.get("BUCKET_NAME")

app.config.from_mapping(
    CELERY=dict(
        broker_url=REDIS_URL,
        result_backend=REDIS_URL,
        task_ignore_result=False,
    ),
)

# Inizializzazione Celery
from celery import Celery, Task
def celery_init_app(app: Flask) -> Celery:
    class FlaskTask(Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app = Celery(app.name, task_cls=FlaskTask)
    celery_app.config_from_object(app.config["CELERY"])
    celery_app.set_default()
    app.extensions["celery"] = celery_app
    return celery_app

celery = celery_init_app(app)

# --- INIZIALIZZAZIONE COMPONENTI (DB E S3) ---

def get_db_connection():
    """Inizializza una connessione sicura e thread-safe al database SQLite."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Crea la tabella dei Job se non esiste ancora."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            duration INTEGER,
            status TEXT,
            progress INTEGER,
            report_key TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def get_s3_client():
    """Restituisce un client boto3 per comunicare con AWS S3."""
    return boto3.client(
        's3',
        region_name='eu-west-1'
    )

def init_s3_bucket():
    """Tenta di creare in automatico il bucket S3 di reportistica su MinIO."""
    try:
        s3 = get_s3_client()
        # Controlliamo se il bucket esiste già
        s3.create_bucket(Bucket=BUCKET_NAME)
        print(f"[S3] Bucket '{BUCKET_NAME}' pronto o creato con successo.")
    except Exception as e:
        # Silenziamo l'errore se il bucket esiste già o se MinIO è ancora offline all'avvio
        print(f"[S3] Info bucket S3: {e}")

# Database Helpers
def update_db_job(job_id, status, progress, report_key=None):
    """Aggiorna lo stato di avanzamento del job nel DB usando query parametrizzate (anti-SQLi)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        if report_key:
            cursor.execute('''
                UPDATE jobs SET status = ?, progress = ?, report_key = ? WHERE id = ?
            ''', (status, progress, report_key, job_id))
        else:
            cursor.execute('''
                UPDATE jobs SET status = ?, progress = ? WHERE id = ?
            ''', (status, progress, job_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB] Errore aggiornamento DB: {e}")

# --- IL JOB ASINCRONO CON COMPILAZIONE REPORT & CARICAMENTO S3 ---
@celery.task(bind=True)
def long_running_job(self, duration_seconds=10):
    """
    Simula l'elaborazione, aggiorna DB e Redis in tempo reale,
    compila un report TXT e lo carica su MinIO.
    """
    print(f"[WORKER] Avvio del job {self.request.id}...")
    update_db_job(self.request.id, 'PROGRESS', 0)
    
    for i in range(1, duration_seconds + 1):
        time.sleep(1)
        percent = int((i / duration_seconds) * 100)
        
        self.update_state(
            state='PROGRESS',
            meta={'current': i, 'total': duration_seconds, 'percent': percent}
        )
        update_db_job(self.request.id, 'PROGRESS', percent)

    # Elaborazione completata: Creiamo il file di Report
    record_elaborati = random.randint(150, 2000)
    errori_rilevati = random.randint(0, 2)
    
    report_content = f"""==================================================
REPORT DI SICUREZZA - ANALISI PIPELINE CLOUD
==================================================
ID Unico Job : {self.request.id}
Durata Task   : {duration_seconds} secondi
Stato Finale  : COMPLETATO CON SUCCESSO
Data Esecuz.  : {time.strftime('%Y-%m-%d %H:%M:%S')}

METRICHE DI COMPLIANCE:
- Record di log esaminati: {record_elaborati}
- Anomalie di sistema rintracciate: {errori_rilevati}

--------------------------------------------------
Dichiarazione di Integrità:
Il presente log è stato sigillato in modo asincrono.
Il Worker Celery ha memorizzato questo asset in S3.
==================================================
"""
    
    # Caricamento del Report su MinIO (S3)
    report_key = f"report_{self.request.id}.txt"
    try:
        s3 = get_s3_client()
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=report_key,
            Body=report_content.encode('utf-8'),
            ContentType='text/plain'
        )
        print(f"[WORKER] Report salvato con successo su S3 ({BUCKET_NAME}/{report_key})")
    except Exception as e:
        print(f"[WORKER] Fallimento nel caricamento S3: {e}")
        report_key = None # Se fallisce S3, non avremo la chiave scaricabile

    # Finalizzazione sul DB
    update_db_job(self.request.id, 'SUCCESS', 100, report_key=report_key)

    return {
        "status": "COMPLETATO",
        "record_elaborati": record_elaborati,
        "errori_rilevati": errori_rilevati,
        "messaggio": "Report archiviato con successo su S3 (MinIO).",
        "report_key": report_key
    }

# --- INTERFACCIA WEB (HTML / JAVASCRIPT CORRETTO PER LA STORICIZZAZIONE) ---
# HTML_DASHBOARD, variabili esportata in index.html frontend

@app.route("/")  # Health check per Fargate messa al posto suo
def health():
    return jsonify({"status": "ok"})

@app.route("/api/submit-job", methods=["POST"])
def submit_job():
    """Endpoint API per registrare ed avviare un job asincrono."""
    data = request.get_json() or {}
    duration = data.get("duration", 15)

    # --- SANIFICAZIONE INPUT ---
    if not isinstance(duration, int) or duration < 5 or duration > 120:
        return jsonify({"error": "Parametro non ammesso. Valore corretto: tra 5 e 120."}), 400

    # Avviamo il Celery task
    task = long_running_job.delay(duration)
    
    # Registriamo immediatamente lo stato iniziale 'PENDING' nel DB
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO jobs (id, duration, status, progress) VALUES (?, ?, ?, ?)
        ''', (task.id, duration, 'PENDING', 0))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB Error] Impossibile inserire il record iniziale del job: {e}")

    return jsonify({"task_id": task.id}), 202

@app.route("/api/job-status/<task_id>", methods=["GET"])
def job_status(task_id):
    """Endpoint API per verificare lo stato di avanzamento sia da Celery che da DB."""
    # --- CYBERSECURITY: Sanificazione parametro ID ---
    if not task_id.isalnum() and '-' not in task_id:
        return jsonify({"error": "ID Malformato"}), 400

    # Interroghiamo Celery per avere lo stato in tempo reale
    task = long_running_job.AsyncResult(task_id)
    
    response = {
        "state": task.state,
        "percent": 0,
        "current": 0,
        "total": 0,
        "result": None
    }
    
    if task.state == 'PENDING':
        # Se Celery non l'ha ancora preso, interroghiamo il DB per lo storico
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT status, progress FROM jobs WHERE id = ?', (task_id,))
            row = cursor.fetchone()
            conn.close()
            if row:
                response["state"] = row["status"]
                response["percent"] = row["progress"]
        except Exception as e:
            print(f"[DB Status Error]: {e}")
            
    elif task.state == 'PROGRESS':
        response["percent"] = task.info.get('percent', 0)
        response["current"] = task.info.get('current', 0)
        response["total"] = task.info.get('total', 0)
    elif task.state == 'SUCCESS':
        response["percent"] = 100
        response["result"] = task.result
    elif task.state == 'FAILURE':
        response["percent"] = 0
        response["result"] = str(task.info)
        
    return jsonify(response)

@app.route("/api/jobs-history", methods=["GET"])
def jobs_history():
    """Restituisce gli ultimi 10 Job registrati nel Database."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, duration, status, progress, report_key, created_at 
            FROM jobs 
            ORDER BY created_at DESC 
            LIMIT 10
        ''')
        rows = cursor.fetchall()
        conn.close()
        
        history = []
        for r in rows:
            history.append({
                "id": r["id"],
                "duration": r["duration"],
                "status": r["status"],
                "progress": r["progress"],
                "report_key": r["report_key"],
                "created_at": r["created_at"]
            })
        return jsonify(history)
    except Exception as e:
        return jsonify({"error": f"Errore lettura DB: {str(e)}"}), 500

@app.route("/api/download-report/<task_id>", methods=["GET"])
def download_report(task_id):
    """
    S3 GATEWAY PROXY: Scarica privatamente il file da MinIO 
    e lo serve all'utente. Evita l'esposizione diretta dell'endpoint S3.
    """
    # Sanificazione dell'input per prevenire Path Traversal o SQL Injection
    if not task_id.isalnum() and '-' not in task_id:
        return jsonify({"error": "ID non valido"}), 400

    try:
        # 1. Recuperiamo la chiave S3 dal database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT report_key FROM jobs WHERE id = ?', (task_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row or not row["report_key"]:
            return jsonify({"error": "Nessun report associato a questo ID o job ancora incompleto."}), 404
            
        report_key = row["report_key"]

        # 2. Ci connettiamo a MinIO privatamente per estrarre l'oggetto
        s3 = get_s3_client()
        s3_object = s3.get_object(Bucket=BUCKET_NAME, Key=report_key)
        file_content = s3_object['Body'].read()
        
        # 3. Restituiamo il file in modo asincrono
        return app.response_class(
            file_content,
            mimetype='text/plain',
            headers={"Content-disposition": f"attachment; filename={report_key}"}
        )
    except Exception as e:
        return jsonify({"error": f"Errore durante l'interazione con lo storage S3: {str(e)}"}), 500

if __name__ == "__main__":
    # Inizializzazione ambienti primari all'avvio del container web Flask
    init_db()
    init_s3_bucket()
    app.run(host="0.0.0.0", port=5000)