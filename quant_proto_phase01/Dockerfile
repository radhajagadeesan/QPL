# SPLASH 2026 Artifact Evaluation image for Granthi / QPL.
#
# Base: OCaml team's official Debian 12 + OCaml 4.14 image.
# Adds: dune, Python 3.11 venv, pytket 2.11.0, the QPL source tree.
#
# Build:   docker build -t granthi-ae .
# Run:     docker run --rm -it granthi-ae
# KTT:     docker run --rm granthi-ae artifact/kick-the-tires.sh
# Full:    docker run --rm granthi-ae artifact/reproduce.sh

FROM ocaml/opam:debian-12-ocaml-4.14

# --- System deps -----------------------------------------------------------
# apt runs as root; the ocaml/opam image drops to user `opam` afterwards.
USER root
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip \
        build-essential git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# --- OCaml toolchain -------------------------------------------------------
USER opam
WORKDIR /home/opam
# The base image already has an opam switch. Ensure dune is present at a
# version compatible with (lang dune 3.0).
RUN opam update && \
    opam install -y dune.3.14.0

# --- Python venv with pytket ----------------------------------------------
# Kept in /home/opam/venv, activated implicitly by prepending to PATH.
RUN python3 -m venv /home/opam/venv && \
    /home/opam/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /home/opam/venv/bin/pip install --no-cache-dir pytket==2.11.0 pytest

ENV PATH="/home/opam/venv/bin:${PATH}"
ENV PYTHONPATH="/work/python/src"

# --- Source tree -----------------------------------------------------------
# COPY runs as root; chown so the opam user can build.
USER root
COPY --chown=opam:opam . /work
WORKDIR /work
USER opam

# Bake `opam env` so `dune` works in every RUN and every CMD.
RUN eval $(opam env) && cd ocaml && dune build

# Make the artifact scripts executable (they are already, but be defensive).
RUN chmod +x artifact/kick-the-tires.sh artifact/reproduce.sh || true

# Default: drop into a shell with everything ready.
SHELL ["/bin/bash", "-lc"]
CMD ["bash", "-lc", "eval $(opam env) && exec bash"]
