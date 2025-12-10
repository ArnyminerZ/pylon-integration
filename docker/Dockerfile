# Use a lightweight Python image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir pyserial paho-mqtt

# Copy the script into the container
COPY pylon2mqtt.py .

# Set Python to unbuffered mode (so logs show up instantly in Docker)
ENV PYTHONUNBUFFERED=1

# Run the script
CMD ["python", "pylon2mqtt.py"]
