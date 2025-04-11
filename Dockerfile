FROM python:3.13

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app .

CMD ["python", "bot.py"]
