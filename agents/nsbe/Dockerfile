FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY agents_shared /app/agents_shared
COPY agents /app/agents
COPY campuses /app/campuses

# Which campus pack to serve; identity, copy, and data all come from it.
ENV CAMPUS_ID=ucsc

EXPOSE 8024

CMD ["python", "-m", "agents.nsbe.agent"]
