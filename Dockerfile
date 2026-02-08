FROM python:3.12-alpine

WORKDIR /app

COPY requirements.txt .
RUN apk add --no-cache bash && pip install --no-cache-dir -r requirements.txt

COPY . .

COPY entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
