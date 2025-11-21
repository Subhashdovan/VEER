# Use the official Playwright base image
FROM mcr.microsoft.com/playwright:v1.45.0-jammy

# Set working directory inside the container
WORKDIR /app

# Install Python and pip inside the Playwright image
RUN apt-get update && \
    apt-get install -y python3 python3-pip && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements file and install dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the rest of the application files (including the python script and cookies)
COPY . .

# Set environment variable for Python output
ENV PYTHONUNBUFFERED 1

# Default command to start the web service
# Use python3 instead of python for clarity
CMD ["python3", "e2e_web_tool.py"]
