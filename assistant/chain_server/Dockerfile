# Lingi7 Shopping Assistant — Chain Server

FROM python:3.11-slim

WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code and config
COPY ./src ./app

# Set environment variables
ENV PYTHONPATH=/app
ENV SHARED_CONFIG_ROOT=/app/shared/configs

# Expose the port the app runs on
EXPOSE 8009

# Command to run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8009", "--reload"]