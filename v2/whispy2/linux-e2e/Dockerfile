# The Linux image of whispy2's end-to-end checks (see README.md next to this file):
# the build tools, an X server (Xvfb), a Wayland compositor (sway, headless),
# PulseAudio for a virtual microphone, and the tools that drive them.
FROM rust:1-bookworm
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    cmake clang libclang-dev pkg-config libasound2-dev libasound2-plugins libxkbcommon-dev \
    xvfb xdotool xterm x11-utils xclip \
    sway foot wtype \
    dbus dbus-x11 libnotify-bin python3-dbus python3-gi libglib2.0-bin \
    pulseaudio pulseaudio-utils socat curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN rustup component add clippy rustfmt
