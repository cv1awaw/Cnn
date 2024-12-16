FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy only the requirements first for caching benefits
COPY requirements.txt /app/requirements.txt

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Now copy the rest of the application files
COPY . /app

# Expose a port if needed (e.g., for debugging or specific hosting environments)
EXPOSE 8080

# Set the default command to run your bot
CMD ["python", "main.py"]
