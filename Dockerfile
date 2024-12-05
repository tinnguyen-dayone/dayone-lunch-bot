FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy project files without .env
COPY . .

# Set CMD to run the application directly with unbuffered output
CMD ["python3", "-u", "main.py"]