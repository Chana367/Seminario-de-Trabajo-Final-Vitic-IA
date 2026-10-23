# Python 3.11 para compatibilidad con las dependencias geoespaciales fijadas.
FROM python:3.11-slim

# Salida sin buffer y sin archivos de bytecode.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Rasterio, PyProj, NumPy y h5py publican wheels manylinux para Python 3.11.
# Se instalan wheels binarios; los requisitos se copian antes para reutilizar la cache.
COPY requirements.txt .
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt

# Código de la aplicación
COPY . .

# Render inyecta la variable PORT, uvicorn la lee de acá
EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
