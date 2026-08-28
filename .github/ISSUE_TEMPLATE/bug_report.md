---
name: Bug report
about: Report something that isn't working
title: "[Bug] "
labels: bug
---

## Description

A clear description of what the bug is.

## Steps to reproduce

1. ...
2. ...
3. ...

## Expected behavior

What you expected to happen.

## Actual behavior

What actually happened.

## Environment

- OS (macOS version, or Linux distro + X11/Wayland):
- Whispy version / commit:
- Language spoken:

<!--
Whispy recognizes 25 languages and detects them automatically — there is no
language setting. Speech outside this list will not transcribe, and that is
expected rather than a bug:

Bulgarian, Croatian, Czech, Danish, Dutch, English, Estonian, Finnish, French,
German, Greek, Hungarian, Italian, Latvian, Lithuanian, Maltese, Polish,
Portuguese, Romanian, Slovak, Slovenian, Spanish, Swedish, Russian, Ukrainian.

If nothing at all was typed, check ~/.whispy.log first: a line saying the
recording was "too short", "near-silent", or that "No speech detected" means a
guard discarded the clip before transcription, which is usually a microphone or
input-level problem rather than a language one.
-->

## Logs

Relevant lines from `~/.whispy.log` and `~/.whispy-error.log`:

```
paste logs here
```
