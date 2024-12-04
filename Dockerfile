# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt /app/
RUN python -m venv --copies /opt/venv
RUN . /opt/venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt

# Copy project
COPY . /app/

# Run the application
CMD ["python", "main.py"]
