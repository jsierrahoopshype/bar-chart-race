FROM python:3.12-slim

# System dependencies: ffmpeg + DejaVu fonts.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Download Poppins fonts from GitHub (used by config.py _find_font).
RUN mkdir -p /usr/share/fonts/truetype/google-fonts && \
    python -c "import urllib.request; urllib.request.urlretrieve('https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf', '/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf')" && \
    python -c "import urllib.request; urllib.request.urlretrieve('https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Medium.ttf', '/usr/share/fonts/truetype/google-fonts/Poppins-Medium.ttf')" && \
    python -c "import urllib.request; urllib.request.urlretrieve('https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Regular.ttf', '/usr/share/fonts/truetype/google-fonts/Poppins-Regular.ttf')" && \
    python -c "import urllib.request; urllib.request.urlretrieve('https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Light.ttf', '/usr/share/fonts/truetype/google-fonts/Poppins-Light.ttf')" && \
    fc-cache -f

# Create non-root user (HF Spaces requirement).
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH

WORKDIR /app

# Install Python dependencies.
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy application code.
COPY --chown=user bar_race/ bar_race/
COPY --chown=user app.py .

# Copy headshot assets.
COPY --chown=user assets/headshots/ assets/headshots/

EXPOSE 7860

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:7860", "--timeout", "300", "--workers", "1", "--threads", "4"]
