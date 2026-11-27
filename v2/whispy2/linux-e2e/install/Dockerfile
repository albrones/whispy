# A fresh Debian with systemd as PID 1, for the installation check
# (../install.sh): no Rust, no compiler, no cmake, no Whispy. Only what a
# desktop session would bring (sudo, an X server, PulseAudio, a terminal) and
# the tools that drive the test.
FROM debian:bookworm
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    systemd systemd-sysv dbus dbus-user-session sudo ca-certificates curl git python3 \
    xvfb xdotool xterm x11-utils pulseaudio pulseaudio-utils libasound2-plugins \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -s /bin/bash e2e && echo 'e2e ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/e2e \
    && mkdir -p /var/lib/systemd/linger && touch /var/lib/systemd/linger/e2e
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
