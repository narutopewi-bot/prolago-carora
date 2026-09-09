FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema si fueran necesarias
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Inicializar y migrar base de datos si no existe
RUN python -c "from backend.database import engine, Base; Base.metadata.create_all(bind=engine)"

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
