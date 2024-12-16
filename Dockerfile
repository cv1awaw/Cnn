# Use a slim Python 3.11 base image for smaller size and faster startup
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy in requirements first (so Docker can cache this layer)
COPY requirements.txt /app/

# Install requirements without caching to keep image smaller
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your bot code
# If your main code is in a file named bot.py, or main.py, adjust accordingly
COPY main.py /app/

# Expose the port if needed (not strictly required for Telegram bots, they poll)
# EXPOSE 8080

# Run the application
CMD ["python", "main.py"]
