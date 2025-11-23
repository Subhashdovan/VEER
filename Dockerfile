# Use the official Playwright base image (Latest version is often better)
FROM mcr.microsoft.com/playwright:v1.45.0-jammy

# Set working directory inside the container
WORKDIR /app

# Install Python and pip inside the Playwright image
RUN apt-get update && \
    apt-get install -y python3 python3-pip && \
    rm -rf /var/lib/apt/lists/*

# Fix: Manually set the browser path environment variable to where browsers are installed in this image.
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/lib/chromium/

# Copy requirements file and install dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the rest of the application files
COPY . .

# Set environment variable for Python output
ENV PYTHONUNBUFFERED 1

# Default command to start the web service
CMD ["python3", "e2e_web_tool.py"]
