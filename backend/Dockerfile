# image_trend_monetizer/backend/Dockerfile

# Use an official Python runtime as a parent image
# Choose a version compatible with your development environment
# arm64v8/python is specifically for ARM64 like Raspberry Pi 4/5
# Or just use 'python:3.10-slim' which often supports multi-arch
FROM python:3.10-slim
# FROM arm64v8/python:3.10-slim # More explicit for Pi

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file first to leverage Docker cache
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# --no-cache-dir reduces image size
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend application code into the container
COPY . .

# Create the uploads directory structure within the image
# Although the volume mount will ultimately manage this space
RUN mkdir -p /app/uploads/original /app/uploads/proof /app/uploads/edited

# Make port 5000 available to the network *outside* this container
# Flask default development server runs on 5000
EXPOSE 5000

# Define environment variables (optional, can be overridden by docker-compose)
# ENV FLASK_APP=app.py # Often needed if using 'flask run'
# ENV FLASK_RUN_HOST=0.0.0.0

# Command to run the application when the container launches
# Use Gunicorn for a more production-ready server than 'python app.py'
# Install Gunicorn first: RUN pip install --no-cache-dir gunicorn
CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:5000", "app:app"]

# # --- OR --- Simpler for initial testing (uses Flask's built-in server):
# CMD ["python", "app.py"]