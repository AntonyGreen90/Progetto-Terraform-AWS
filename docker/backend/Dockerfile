FROM python:3.11-slim

RUN mkdir -p /data

RUN useradd appuser && chown -R appuser:appuser /data

COPY app.py requirements.txt . 

RUN pip install -r requirements.txt 
# questo RUN va prima di USER appuser perchè va lanciato da root
USER appuser

# EXPOSE 5000

CMD ["python", "app.py"] 