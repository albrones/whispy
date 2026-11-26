# The image of the Omarchy checks (omarchy.sh): Quickshell, built from source
# (no Debian package), to run the bar panel's real Service.qml against a real
# whispy2; and the Wayland session, microphone and tools of the Linux checks.
# whispy2 itself is the one ../run.sh builds in the bookworm image.
FROM debian:trixie
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    git ca-certificates cmake ninja-build g++ pkg-config \
    qt6-base-dev qt6-base-private-dev qt6-declarative-dev qt6-declarative-private-dev qt6-shadertools-dev \
    spirv-tools libcli11-dev libdrm-dev libgbm-dev libegl-dev libvulkan-dev libglib2.0-dev \
    qml6-module-qtquick qml6-module-qtqml-workerscript \
    sway foot wtype jq socat iproute2 lua5.4 dbus dbus-x11 libnotify-bin \
    pulseaudio pulseaudio-utils libasound2-plugins libxkbcommon0 \
    && rm -rf /var/lib/apt/lists/*
# Omarchy runs Quickshell 0.3; only what the panel's Service.qml imports
# (Quickshell, Quickshell.Io) is needed, so the optional modules are off.
RUN git clone --depth 1 --branch v0.3.2 https://github.com/quickshell-mirror/quickshell /qs-src \
    && cd /qs-src && cmake -GNinja -B build -DCMAKE_BUILD_TYPE=RelWithDebInfo -DDISTRIBUTOR=whispy-e2e \
      -DCRASH_HANDLER=OFF -DUSE_JEMALLOC=OFF -DWAYLAND=OFF -DX11=OFF -DHYPRLAND=OFF -DI3=OFF -DSCREENCOPY=OFF \
      -DSERVICE_PIPEWIRE=OFF -DSERVICE_STATUS_NOTIFIER=OFF -DSERVICE_MPRIS=OFF -DSERVICE_PAM=OFF \
      -DSERVICE_POLKIT=OFF -DSERVICE_GREETD=OFF -DSERVICE_UPOWER=OFF -DSERVICE_NOTIFICATIONS=OFF \
      -DBLUETOOTH=OFF -DNETWORK=OFF \
    && cmake --build build && cmake --install build && rm -rf /qs-src
