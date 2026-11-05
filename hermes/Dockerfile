# Build context: hermes/. Inherit upstream USER, ENTRYPOINT, and CMD unchanged.
FROM nousresearch/hermes-agent@sha256:39c4ac5a8eaecddc525cd680eb4bda1143f2b12e8f21e2d63c2d5d471a8390c8

COPY apply_patch.py check_voice_dependencies.py requirements-voice.txt requirements-voice.lock /opt/xiaoxi/
COPY patches/hermes.patch patches/manifest.json /opt/xiaoxi/patches/
COPY workspace/AGENTS.md /opt/xiaoxi/workspace/AGENTS.md

RUN --network=none python -B /opt/xiaoxi/apply_patch.py --root /opt/hermes \
    && /opt/hermes/.venv/bin/python -I -B /opt/xiaoxi/check_voice_dependencies.py \
       --record /opt/xiaoxi/dependency-before.json

RUN env -i PATH=/opt/hermes/.venv/bin:/usr/local/bin:/usr/bin:/bin \
       HOME=/tmp TMPDIR=/tmp LANG=C.UTF-8 \
       /usr/local/bin/uv pip install --no-config \
       --default-index https://pypi.org/simple --no-python-downloads \
       --python /opt/hermes/.venv/bin/python --no-cache --require-hashes \
       --no-deps -r /opt/xiaoxi/requirements-voice.lock

# Compare all dependency conflicts, check every locked version, then import four
# libraries without constructing models, processing audio, or using network.
RUN --network=none /opt/hermes/.venv/bin/python -I -B \
       /opt/xiaoxi/check_voice_dependencies.py \
       --compare /opt/xiaoxi/dependency-before.json

# Existing upstream node_modules only. No dependency install or network access.
RUN --network=none cd /opt/hermes/web && npm run build

# Whisper weights are not downloaded or assumed present. Mount a reviewed,
# pre-provisioned model directory read-only at /opt/data/whisper-base at deployment.
# Project persona is available at /opt/xiaoxi/workspace/AGENTS.md; the deployment
# chooses its workspace mount through the supported Hermes context mechanism.
