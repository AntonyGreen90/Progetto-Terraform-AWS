import os
import time
import random
import sqlite3
import boto3
from botocore.client import Config
from flask import Flask, jsonify, request, render_template_string

# Configurazione dell'applicazione Flask
app = Flask(__name__)

# --- CONFIGURAZIONI AMBIENTALI E SICUREZZA ---
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
DB_PATH = os.environ.get("DB_PATH", "/data/jobs.db") # invece di /jobs.db mancava la cartella /data

# MinIO / S3 config
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "minio:9000") # invece di localhost:9000
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "iso9000")   # accesskey e secret key cambiate
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "sopra8000")
BUCKET_NAME = "reports"

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
    """Restituisce un client boto3 per comunicare privatamente con MinIO."""
    endpoint = MINIO_ENDPOINT
    if not endpoint.startswith("http://") and not endpoint.startswith("https://"):
        endpoint = f"http://{endpoint}"
    return boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
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
HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ITC Cloud & Cyber - Pipeline Avanzata</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen font-sans">
    <div class="container mx-auto px-4 py-8 max-w-4xl">
        
        <!-- Header -->
        <header class="flex items-center justify-between border-b border-gray-800 pb-6 mb-8">
            <div>
                <span class="bg-emerald-500/10 text-emerald-400 text-xs px-3 py-1 rounded-full font-semibold uppercase tracking-wider">Storage & Database Gateway</span>
                <h1 class="text-3xl font-extrabold tracking-tight mt-1 text-white">Pipeline Asincrona con DB & S3</h1>
            </div>
            <div class="text-right">
                <span class="text-xs text-gray-500 block">Stato Infrastruttura</span>
                <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800 mt-1">
                    <span class="h-2 w-2 rounded-full bg-emerald-400 mr-1.5 animate-pulse"></span>
                    S3 + SQLite Online
                </span>
            </div>
        </header>

        <!-- Sottomissione del Job -->
        <div class="bg-gray-800 rounded-xl shadow-lg border border-gray-700 p-6 mb-8">
            <h2 class="text-xl font-bold text-white mb-2">🔧 Sottometti un nuovo Job</h2>
            <p class="text-gray-400 text-sm mb-6">
                Avvia il task. Al termine, il worker scriverà permanentemente lo stato sul <strong>Database SQLite</strong> 
                e caricherà un file di audit su <strong>MinIO S3</strong>. L'app Flask fungerà da Gateway Proxy protetto per farti scaricare il report.
            </p>
            <div class="flex flex-col sm:flex-row items-end gap-4">
                <div class="w-full sm:w-2/3">
                    <label for="duration" class="block text-xs font-semibold uppercase text-gray-400 mb-2">Imposta durata elaborazione (secondi):</label>
                    <input type="number" id="duration" value="15" min="5" max="120" 
                           class="w-full bg-gray-950 border border-gray-700 rounded-lg px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 font-mono">
                </div>
                <div class="w-full sm:w-1/3">
                    <button onclick="submitJob()" 
                            class="w-full bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 text-white font-bold py-3 px-4 rounded-lg transition-colors flex items-center justify-center gap-2 shadow-lg shadow-emerald-900/20">
                        Invia al Worker
                    </button>
                </div>
            </div>
        </div>

        <!-- Sezione Monitoraggio -->
        <div>
            <h2 class="text-xl font-bold text-white mb-4 flex items-center gap-2">
                📊 Tracker dei Job & Persistenza DB
            </h2>
            
            <!-- Caricamento -->
            <div id="no-jobs" class="text-center py-12 border-2 border-dashed border-gray-800 rounded-xl bg-gray-900/50">
                <p class="text-gray-500">Nessun job presente nel database.</p>
            </div>

            <!-- Lista dei Job storicizzati -->
            <div id="jobs-container" class="space-y-4"></div>
        </div>

    </div>

    <script>
        const activeJobs = new Map();

        // Al caricamento della pagina leggiamo lo stato storico dal DB!
        window.addEventListener('DOMContentLoaded', loadHistory);

        async function loadHistory() {
            try {
                const response = await fetch('/jobs-history');
                const jobs = await response.json();
                
                if (jobs.length > 0) {
                    document.getElementById('no-jobs').classList.add('hidden');
                    // Mostriamo prima i vecchi job inserendoli in sequenza
                    jobs.reverse().forEach(job => {
                        addJobToUI(job.id, job.duration, job.status, job.progress, job.report_key);
                        if (job.status === 'PROGRESS' || job.status === 'PENDING') {
                            pollJobStatus(job.id);
                        }
                    });
                }
            } catch (error) {
                console.error("Impossibile caricare la cronologia dal DB:", error);
            }
        }

        async function submitJob() {
            const durationInput = document.getElementById('duration');
            const duration = parseInt(durationInput.value);

            try {
                const response = await fetch('/submit-job', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ duration: duration })
                });
                
                if (!response.ok) {
                    const errorData = await response.json();
                    alert(errorData.error || "Errore di sottomissione");
                    return;
                }

                const data = await response.json();
                addJobToUI(data.task_id, duration, 'PENDING', 0);
                pollJobStatus(data.task_id);

            } catch (error) {
                console.error("Errore di rete durante la sottomissione:", error);
            }
        }

        function addJobToUI(taskId, duration, initialStatus = 'PENDING', progress = 0, reportKey = null) {
            document.getElementById('no-jobs').classList.add('hidden');
            
            // Preveniamo duplicati grafici
            if (document.getElementById(`job-${taskId}`)) return;
            
            const card = document.createElement('div');
            card.id = `job-${taskId}`;
            card.className = "bg-gray-800 border border-gray-700 rounded-xl p-5 shadow-sm transition-all";
            
            let badgeClass = "bg-blue-500/10 text-blue-400 animate-pulse";
            let badgeText = "IN CODA";
            
            if (initialStatus === 'PROGRESS') {
                badgeClass = "bg-amber-500/15 text-amber-400";
                badgeText = "IN ESECUZIONE";
            } else if (initialStatus === 'SUCCESS') {
                badgeClass = "bg-emerald-500/15 text-emerald-400";
                badgeText = "RISOLTO";
            } else if (initialStatus === 'FAILURE') {
                badgeClass = "bg-red-500/15 text-red-400";
                badgeText = "FALLITO";
            }

            const showResult = initialStatus === 'SUCCESS' && reportKey ? '' : 'hidden';

            card.innerHTML = `
                <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
                    <div class="flex items-center gap-2">
                        <span class="bg-gray-700 text-gray-300 text-xs font-mono px-2 py-1 rounded">ID: ${taskId.substring(0,8)}...</span>
                        <span id="status-badge-${taskId}" class="px-2.5 py-0.5 rounded-full text-xs font-semibold ${badgeClass}">
                            ${badgeText}
                        </span>
                    </div>
                    <span class="text-xs text-gray-400">Tempo stimato: ${duration} secondi</span>
                </div>
                
                <div class="w-full bg-gray-950 rounded-full h-3 mb-2 overflow-hidden">
                    <div id="progress-bar-${taskId}" class="bg-emerald-500 h-3 rounded-full transition-all duration-300" style="width: ${progress}%"></div>
                </div>
                
                <div class="flex justify-between text-xs text-gray-400">
                    <span id="progress-text-${taskId}">${initialStatus === 'SUCCESS' ? 'Salvato permanentemente' : 'In attesa del worker...'}</span>
                    <span id="progress-percent-${taskId}">${progress}%</span>
                </div>
                
                <div id="result-${taskId}" class="${showResult} mt-4 pt-3 border-t border-gray-700/50 text-xs font-mono bg-gray-900/50 p-3 rounded border border-gray-800">
                    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <span class="text-emerald-400">✓ Report di sicurezza caricato su MinIO. Scaricabile in modalità "Proxy Sicuro":</span>
                        <a href="/download-report/${taskId}" class="bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-1.5 px-3 rounded text-center transition-all">
                            Scarica Report (S3 Proxy)
                        </a>
                    </div>
                </div>
            `;
            
            document.getElementById('jobs-container').prepend(card);
            activeJobs.set(taskId, { duration, intervalId: null });
        }

        function pollJobStatus(taskId) {
            const intervalId = setInterval(async () => {
                try {
                    const response = await fetch(`/job-status/${taskId}`);
                    const statusData = await response.json();
                    
                    updateJobUI(taskId, statusData);
                    
                    if (statusData.state === 'SUCCESS' || statusData.state === 'FAILURE') {
                        clearInterval(intervalId);
                        activeJobs.delete(taskId);
                    }
                } catch (err) {
                    console.error("Errore durante il polling dello stato:", err);
                }
            }, 1000);
            
            if (activeJobs.has(taskId)) {
                activeJobs.get(taskId).intervalId = intervalId;
            }
        }

        function updateJobUI(taskId, data) {
            const statusBadge = document.getElementById(`status-badge-${taskId}`);
            const progressBar = document.getElementById(`progress-bar-${taskId}`);
            const progressText = document.getElementById(`progress-text-${taskId}`);
            const progressPercent = document.getElementById(`progress-percent-${taskId}`);
            const resultContainer = document.getElementById(`result-${taskId}`);
            
            if (data.state === 'PROGRESS') {
                statusBadge.className = "px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-400";
                statusBadge.innerText = "IN ESECUZIONE";
                
                progressBar.style.width = `${data.percent}%`;
                progressText.innerText = `Processamento in corso e scrittura DB (${data.current}/${data.total}s)`;
                progressPercent.innerText = `${data.percent}%`;
            } else if (data.state === 'SUCCESS') {
                statusBadge.className = "px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-400";
                statusBadge.innerText = "RISOLTO";
                
                progressBar.style.width = "100%";
                progressText.innerText = "Esecuzione completata correttamente!";
                progressPercent.innerText = "100%";
                
                resultContainer.classList.remove('hidden');
                resultContainer.innerHTML = `
                    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <span class="text-emerald-400">✓ Report caricato su S3. Scaricabile in modalità "Proxy Sicuro":</span>
                        <a href="/download-report/${taskId}" class="bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-1.5 px-3 rounded text-center transition-all">
                            Scarica Report (S3 Proxy)
                        </a>
                    </div>
                `;
            } else if (data.state === 'FAILURE') {
                statusBadge.className = "px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-500/15 text-red-400";
                statusBadge.innerText = "FALLITO";
                progressBar.className = "bg-red-500 h-3 rounded-full transition-all";
                progressText.innerText = "Errore durante l'elaborazione del job.";
            }
        }
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_DASHBOARD)

@app.route("/submit-job", methods=["POST"])
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

@app.route("/job-status/<task_id>", methods=["GET"])
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

@app.route("/jobs-history", methods=["GET"])
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

@app.route("/download-report/<task_id>", methods=["GET"])
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