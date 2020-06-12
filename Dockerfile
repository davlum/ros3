FROM python:3.8-slim

COPY requirements.txt /requirements.txt

RUN pip install --no-cache-dir -r /requirements.txt

RUN mkdir /opt/ros3

WORKDIR /opt/ros3

COPY . .

CMD ["python", "main.py", "-H", "0.0.0.0", "-p2000"]

