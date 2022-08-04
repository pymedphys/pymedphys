# Build this image with:
# docker build --tag pymedphys .

# Run this image with:
# docker run --publish 8501:8501 --name pymedphys pymedphys

# View the result by opening browser at http://localhost:8501

# Stop the container by running the following in a separate terminal:
# docker stop pymedphys

FROM python:3.10-slim

ENV PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=100 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

COPY . .

RUN pip install -r requirements.txt
CMD ["pymedphys", "gui"]
