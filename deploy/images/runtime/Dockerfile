# Shared deterministic services; no repository-wide COPY or runtime credentials.
FROM python@sha256:a1165e272e578941b84abc79e4ab38a0305cd12803a5c4247979ac7655f4d641
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /repo
COPY services/bridge/requirements.txt /repo/requirements.txt
RUN pip install --no-cache-dir --disable-pip-version-check -r /repo/requirements.txt
COPY scripts/check_repository.py /repo/scripts/check_repository.py
COPY schemas/telemetry.schema.json /repo/schemas/telemetry.schema.json
COPY services/bridge/validator.py services/bridge/read_gateway.py services/bridge/inference_egress.py services/bridge/dashboard_ingress.py /repo/services/bridge/
RUN chmod -R a+rX /repo && install -d -m 0700 -o 10001 -g 10001 /var/lib/xiaoxi
USER 10001:10001
ENTRYPOINT ["python"]
