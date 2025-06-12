FROM python:3.13.4-slim
COPY . /app/
WORKDIR /app

RUN pip install -r requirements.txt
EXPOSE 8089
CMD ["sh", "-c", "locust -f main.py,executors $LOCUST_OPTIONS"]