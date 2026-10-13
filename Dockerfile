FROM python:3.12-slim
WORKDIR /app
COPY studybridge ./studybridge
COPY data ./data
COPY tests ./tests
RUN useradd --create-home app && mkdir -p var && chown -R app /app
USER app
ENV PYTHONDONTWRITEBYTECODE=1
EXPOSE 8765
# Bind to 0.0.0.0 inside the container only; publish it on 127.0.0.1 on the host.
ENTRYPOINT ["python", "-m", "studybridge", "--tier", "TRANSACT"]
CMD ["web", "--host", "0.0.0.0"]
