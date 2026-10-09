# RollbackIQ demo workload image.
#
# The same image serves both releases; the release identity and any injected
# fault arrive as environment variables from the deployment (later, from GitLab
# CI/CD), which is what makes "roll back to the previous release" a change of
# deployment inputs rather than a rebuild.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./

# Release metadata, populated by the deployment. Defaults describe a local run
# so the image is honest about being unlabelled when nothing sets them.
ARG RELEASE_VERSION=v1
ENV RELEASE_VERSION=${RELEASE_VERSION} \
    RELEASE_COMMIT_SHA=local \
    RELEASE_PIPELINE_ID=local \
    RELEASE_IMAGE_DIGEST=local \
    DEPLOY_ENV=demo-staging \
    BASE_LATENCY_MS=20 \
    FAULT_LATENCY_MS=0 \
    FAULT_ERROR_RATE=0

EXPOSE 8000

HEALTHCHECK --interval=5s --timeout=2s --start-period=3s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
