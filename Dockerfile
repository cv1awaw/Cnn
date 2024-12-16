# Use a slim base image
FROM python:3.9-slim

# Create a working directory
WORKDIR /app

# Copy only requirements to leverage caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the source code
COPY . .

# Final command
CMD ["python", "main.py"]
