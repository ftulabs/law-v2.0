#!/usr/bin/env bash
# Cross-build the arm64 image on a bigger x86_64 host (here: 'minh') and ship it to the
# Jetson Nano. JetPack 4.6's Python 3.6 is too old for the app, so we run our own runtime
# inside an arm64 container instead of installing on the host.
#
# Requires on the build host: docker + buildx with a builder that lists linux/arm64
# (QEMU binfmt registered — `docker run --rm --privileged tonistiigi/binfmt --install arm64`
# if not). Run this FROM the repo root.
set -euo pipefail

IMG="${IMG:-veritrade:arm64}"
NANO="${NANO:-minh@jetson-nano}"            # ssh target of the Nano (reachable from here)

echo ">> [1/3] cross-building $IMG for linux/arm64 (QEMU — slow; MAX_JOBS capped in Dockerfile)"
docker buildx build --platform linux/arm64 -t "$IMG" --load .

echo ">> [2/3] shipping image to $NANO over ssh (docker save | gzip | docker load)"
docker save "$IMG" | gzip -1 | ssh "$NANO" 'gunzip | docker load'

echo ">> [3/3] (re)starting the container on $NANO"
ssh "$NANO" 'bash -s' < deploy/run_on_jetson.sh

echo ">> done — open http://<nano-ip>:8501"
