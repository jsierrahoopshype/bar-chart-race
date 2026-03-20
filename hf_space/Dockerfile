FROM python:3.12-slim

# System dependencies: ffmpeg + DejaVu fonts (fallback for theme font families).
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        fonts-dejavu-core \
        wget \
        unzip \
    && rm -rf /var/lib/apt/lists/*

# Download Poppins fonts from Google Fonts (used by config.py _find_font).
RUN mkdir -p /usr/share/fonts/truetype/google-fonts && \
    wget -q "https://fonts.google.com/download?family=Poppins" -O /tmp/poppins.zip && \
    unzip -o /tmp/poppins.zip -d /usr/share/fonts/truetype/google-fonts/ && \
    rm /tmp/poppins.zip && \
    fc-cache -f

WORKDIR /app

# Install Python dependencies.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code.
COPY bar_race/ bar_race/
COPY app.py .

# Copy headshot assets.
COPY assets/headshots/ assets/headshots/

EXPOSE 7860

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:7860", "--timeout", "300", "--workers", "1", "--threads", "4"]
