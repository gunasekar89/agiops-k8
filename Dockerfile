FROM python:3.12-slim AS runtime

ARG HOLMES_VERSION=0.40.0
ARG TARGETARCH=amd64

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL -o /usr/local/bin/kubectl \
       "https://dl.k8s.io/release/v1.31.0/bin/linux/${TARGETARCH}/kubectl" \
    && chmod +x /usr/local/bin/kubectl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . "holmesgpt==${HOLMES_VERSION}"

RUN useradd --create-home --uid 10001 console
USER 10001
ENTRYPOINT ["holmes-console"]
CMD ["--help"]
