FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 METEO_HOST=0.0.0.0 METEO_NO_BROWSER=1 METEO_DATA_DIR=/data
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 meteo \
    && mkdir /data && chown meteo:meteo /data
COPY --chown=meteo:meteo . .
USER meteo
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/api/health', timeout=3)"
CMD ["python", "run.py", "--no-browser"]
