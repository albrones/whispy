# Whispy Homebrew formula.
#
# This file belongs in a separate tap repo: github.com/albrones/homebrew-whispy
# at path Formula/whispy.rb. Once pushed there, users install with:
#
#   brew install albrones/whispy/whispy
#   brew services start whispy
#
# Note: faster-whisper pulls a heavy dependency tree (torch, ctranslate2, ...),
# so we do NOT vendor those as Homebrew `resource` blocks. Instead we create a
# venv in libexec and pip-install the package. This is non-canonical for
# homebrew-core but fine for a personal tap.
class Whispy < Formula
  desc "Private, local voice dictation for macOS (hold Fn, speak, release)"
  homepage "https://github.com/albrones/whispy"
  # url + sha256 below are auto-bumped per release by .github/workflows/release.yml
  # (triggered on a `v*` tag push) and pushed to the homebrew-whispy tap. To set
  # them by hand instead:
  #   curl -fsSL https://github.com/albrones/whispy/archive/refs/tags/v0.1.0.tar.gz | shasum -a 256
  url "https://github.com/albrones/whispy/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "REPLACE_WITH_TARBALL_SHA256"
  license "GPL-3.0-or-later"
  head "https://github.com/albrones/whispy.git", branch: "main"

  depends_on "python@3.12"
  depends_on :macos
  depends_on "sox"

  def install
    # The daemon entry point (whispy_daemon.py) and icons/ live at the repo root,
    # not inside the Python package, so keep the whole tree in libexec.
    libexec.install Dir["*"]

    venv_python = libexec/"venv/bin/python"
    system Formula["python@3.12"].opt_bin/"python3.12", "-m", "venv", libexec/"venv"
    system libexec/"venv/bin/pip", "install", "--upgrade", "pip"
    system libexec/"venv/bin/pip", "install", libexec, "Pillow"

    # Generate the menu bar icons into libexec/icons.
    system venv_python, libexec/"generate_icons.py"
  end

  service do
    run [opt_libexec/"venv/bin/python", opt_libexec/"whispy_daemon.py"]
    keep_alive true
    run_at_load true
    working_dir opt_libexec
    log_path "#{Dir.home}/.whispy.log"
    error_log_path "#{Dir.home}/.whispy-error.log"
    environment_variables PATH: "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
  end

  def caveats
    <<~EOS
      Whispy runs as a background service. Start it with:
        brew services start whispy

      Grant these permissions to the bundled Python binary:
        #{opt_libexec}/venv/bin/python
      in System Settings -> Privacy & Security:
        - Microphone
        - Accessibility
        - Input Monitoring

      A `brew upgrade` can change the binary path above; re-grant the
      permissions if dictation stops working after an upgrade.

      The Whisper model downloads automatically on first use.
      Status check: curl http://localhost:9090/status
    EOS
  end

  test do
    # The package imports cleanly inside its venv.
    system libexec/"venv/bin/python", "-c", "import whispy"
  end
end
