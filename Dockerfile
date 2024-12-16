# Use a lightweight Python base image
FROM python:3.9-slim

# Create and set the working directory in the container
WORKDIR /app

# Copy only requirements first for Docker layer caching
COPY requirements.txt .

# Install dependencies without caching
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY . .

# Final command to run the bot
CMD ["python", "main.py"]
