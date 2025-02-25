# Use the official Python slim image.
FROM python:3.9-slim

# Install Docker CLI (and its dependencies) so that your app can execute docker commands.
RUN apt-get update && \
    apt-get install -y docker.io && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory in the container.
WORKDIR /app

# Copy and install Python dependencies.
COPY requirements.txt requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy your application code.
COPY . .

# Expose the port that your app listens on.
EXPOSE 5000

# Run the app with Gunicorn.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "main:app"]
