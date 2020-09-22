FROM python:3.7-slim as app

RUN mkdir /opt/ros3 && cd /opt/ros3

WORKDIR /opt/ros3

COPY Pipfile .
COPY Pipfile.lock .

RUN pip install --no-cache-dir pipenv && pipenv install

COPY . .

CMD ["pipenv", "run", "python", "main.py", "-H", "0.0.0.0", "-p2000"]

FROM app AS test

RUN pipenv install --dev
