FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONUTF8=1 \
    HARVESTSHIELD_ENV=production HARVESTSHIELD_READ_ONLY=true \
    HARVESTSHIELD_DATA_DIR=/state/data HOME=/tmp
WORKDIR /app
COPY requirements-lock.txt ./
RUN pip install --no-cache-dir -r requirements-lock.txt && pip check \
    && groupadd --gid 10001 harvest && useradd --uid 10001 --gid 10001 --no-create-home harvest \
    && mkdir -p /state && chown 10001:10001 /state
COPY --chown=10001:10001 backend ./backend
COPY --chown=10001:10001 frontend ./frontend
COPY --chown=10001:10001 deployment/bootstrap.py deployment/__init__.py ./deployment/
COPY --chown=10001:10001 .streamlit ./.streamlit
COPY --chown=10001:10001 deployment/seed /seed
USER 10001:10001
EXPOSE 8000 8501
CMD ["python", "-m", "deployment.bootstrap", "api"]
