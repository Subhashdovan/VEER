# Use the official Playwright base image with pre-installed browsers
FROM mcr.microsoft.com/playwright:v1.45.0-jammy

# Set working directory inside the container
WORKDIR /app

# Copy requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files (including the python script and cookies)
COPY . .

# Set environment variable for Python output
ENV PYTHONUNBUFFERED 1

# Default command to start the web service
CMD ["python", "e2e_web_tool.py"]