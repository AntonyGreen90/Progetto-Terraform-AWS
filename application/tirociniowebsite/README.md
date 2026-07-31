🛠️ Laboratorio Cloud & Cyber: Pipeline di Messaggistica Asincrona con DB e S3
==============================================================================

Nelle applicazioni web tradizionali (monolitiche), quando un utente clicca su un pulsante per fare un'operazione pesante (es. generare un report PDF di 100 pagine o analizzare migliaia di log), il server web si "blocca" finché non ha finito. Se l'operazione richiede 30 secondi, il browser dell'utente andrà in timeout e il server non potrà rispondere a nessun altro utente.

Per risolvere questo problema si usa il **Disaccoppiamento Asincrono tramite Coda di Messaggi**.

Bozza di Architettura Logica
----------------------------

Prima di scrivere codice, dobbiamo saper disegnare l'infrastruttura. Ecco come devono essere collegati i componenti e come deve fluire il traffico di rete:

### Flusso dei Dati:

1.  Il client (Browser) interroga l'App Flask sulla porta `5000` (Pubblica) ed invia un Job.

2.  Flask registra il Job come `PENDING` sul Database SQLite e invia un messaggio nella coda Redis.

3.  Il Worker Celery (Privato) preleva il task da Redis, aggiorna progressivamente lo stato sul DB SQLite e, al termine, genera un report testuale.

4.  Il Worker carica il report direttamente su MinIO (S3, Privato).

5.  L'utente clicca su "Scarica". Flask (che ha accesso a MinIO) scarica privatamente il file da S3 e lo passa al browser (Proxy Gateway), proteggendo le credenziali dello storage.

Le Tue Sfide: Cosa devi costruire (Task Pratici)
------------------------------------------------

Il tuo compito è scrivere i file di configurazione Docker per far funzionare l'intero ecosistema. L'applicazione Python (`app.py`) è già pronta e si aspetta di leggere le seguenti variabili d'ambiente:

-   `REDIS_URL` (es. `redis://redis:6379/0`)

-   `DB_PATH` (percorso sul disco del database SQLite, es. `/data/jobs.db`)

-   `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`

Ecco i passaggi che devi implementare autonomamente:

### Task 1: Scrivere il Dockerfile (Hardening di Sicurezza)

Devi creare un file chiamato `Dockerfile` per pacchettizzare l'app Flask e il worker Celery (entrambi usano lo stesso codice Python).

-   **Base Image:** Usa `python:3.11-slim` per mantenere l'immagine leggera (riduce la superficie d'attacco).

-   **Sicurezza ROOT:** Per impostazione predefinita, Docker esegue i comandi come utente `root`. Se un hacker buca la tua app Flask, otterrebbe il controllo del server ospitante! Devi configurare un utente di sistema non privilegiato (chiamalo `appuser`) e dire a Docker di eseguire l'applicazione con quell'utente (`USER appuser`).

-   **Codice:** Copia il file `app.py` all'interno del container ed esponi la porta `5000`.

### Task 2: Configurare l'Orchestratore (docker-compose.yml)

Crea un file `docker-compose.yml` che definisca 4 servizi coordinati:

1.  `redis`: Usa l'immagine ufficiale `redis:7.2-alpine`. Non mappare le sue porte sull'host (non deve essere accessibile da internet!).

2.  `minio`: Usa l'immagine `minio/minio`. Deve avviarsi con il comando `server /data --console-address ":9001"`. Esponi la porta API `9000` e la porta della console web `9001` per poter controllare visivamente i tuoi file da browser. Imposta le credenziali root a tua scelta tramite variabili d'ambiente.

3.  `web`: Deve buildare l'immagine usando il tuo `Dockerfile`. Deve mappare la porta `5000:5000` per consentirti di accedere alla dashboard. Assicurati che dichiari la dipendenza (`depends_on`) da `redis` e `minio`.

4.  `celery_worker`: Deve buildare usando lo stesso `Dockerfile`, ma devi sovrascrivere il comando di avvio per far partire Celery invece di Flask: `celery -A app.celery worker --loglevel=info`.

### Task 3: Configurare l'Isolamento di Rete (Networking)

Non vogliamo che tutti i nostri database siano esposti.

-   All'interno del `docker-compose.yml`, definisci una rete personalizzata di tipo bridge chiamata `secure-app-network`.

-   Collega **tutti e 4** i servizi a questa rete.

-   Assicurati che l'unico servizio che espone la porta `5000` verso il tuo computer sia l'applicazione `web`. Redis non deve avere porte esposte all'esterno!

### Task 4: Configurare la Persistenza dei Dati (Volumi)

Se spegni i container, non vogliamo perdere lo storico dei nostri Job o i file salvati su S3.

-   Definisci due volumi logici in fondo al tuo file Compose: `sqlite-data` e `minio-data`.

-   Monta `sqlite-data` sulla cartella `/data` sia nel container `web` che nel container `celery_worker`. Questo permetterà a entrambi di leggere e scrivere sullo stesso file database `/data/jobs.db`.

-   Monta `minio-data` sulla cartella `/data` del container `minio`.

### Task 5: Scalare i Worker (Verifica delle prestazioni)

Una volta che l'infrastruttura parte correttamente con `docker compose up --build`:

1.  Apri il terminale e lancia il comando per scalare i worker a 3 repliche:

2.  Apri la dashboard (`http://localhost:5000`) e sottometti 6 job contemporaneamente.

3.  Osserva i log sul tuo terminale. Spiega per iscritto nella tua relazione settimanale:

    -   *Come si distribuiscono i Job tra le tre repliche dei Worker?*

    -   *Perché questo approccio rende la tua infrastruttura altamente scalabile e tollerante ai guasti?*