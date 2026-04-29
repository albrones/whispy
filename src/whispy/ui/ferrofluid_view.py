"""Ferrofluid sphere visualization view using CoreGraphics.

Renders a dark sphere with spikes that respond to real-time audio level.
Uses only pyobjc-framework-Quartz (CoreGraphics) — no Metal or OpenGL.
"""

import logging
import math
import time
from typing import Any

from AppKit import NSColor, NSView
from Quartz import (
    CGColorSpaceCreateDeviceGray,
    CGContextAddArc,
    CGContextAddLineToPoint,
    CGContextBeginPath,
    CGContextClosePath,
    CGContextClearRect,
    CGContextConcatCTM,
    CGContextCreateLinearGradient,
    CGContextCreateRadialGradient,
    CGContextDrawGradient,
    CGContextFillPath,
    CGContextGetCTM,
    CGContextGetType,
    CGContextMoveToPoint,
    CGContextSetLineWidth,
    CGContextSetRGBFillColor,
    CGContextSetRGBStrokeColor,
    CGContextSetShadowWithColor,
    CGContextTranslateCTM,
    CGBitmapContextCreateImage,
    CGImageCreateWithImageInRect,
    CGImageDestinationCreateWithURL,
    CGImageDestinationAddImage,
    CGImageDestinationFinalize,
)

logger = logging.getLogger(__name__)


class FerrofluidView(NSView):
    """NSView that renders a ferrofluid sphere responsive to audio level.

    The sphere has 16 spikes radiating outward. Spike height is driven by
    the audio level (0.0 = subtle undulation, 1.0 = dramatic spikes).
    """

    def __init__(self, frame: tuple[float, float, float, float]) -> None:
        super().__init__()
        self._audio_level: float = 0.0
        self._target_level: float = 0.0
        self._last_frame_time: float = 0.0
        self._frame_count: int = 0
        self._spike_phase: float = 0.0
        # Sphere parameters
        self._sphere_radius: float = 50.0
        self._spike_count: int = 16
        self._max_spike_height: float = 45.0
        # Animation
        self._anim_timer: Any = None
        self._fade_target: float = 0.0  # 0 = hide, 1 = fully visible
        self._current_fade: float = 0.0

    # -- Public API --

    def set_audio_level(self, level: float) -> None:
        """Set the target audio level for the next frame."""
        self._target_level = max(0.0, min(1.0, level))

    def set_visible(self, visible: bool) -> None:
        """Set the fade target for show/hide animation."""
        self._fade_target = 1.0 if visible else 0.0

    def start_animation(self) -> None:
        """Start the NSTimer-driven animation loop at ~30fps."""
        if self._anim_timer is not None:
            return
        # We use a Python timer thread instead of NSTimer to avoid rumps
        # timer integration complexity. The drawRect: will be called
        # via performSelectorOnMainThread.
        self._last_frame_time = time.monotonic()
        self._schedule_next_frame()

    def stop_animation(self) -> None:
        """Stop the animation loop."""
        if self._anim_timer is not None:
            self._anim_timer.invalidate()
            self._anim_timer = None

    # -- NSTimer callback (called via performSelectorOnMainThread) --

    def _schedule_next_frame(self) -> None:
        """Schedule the next frame redraw."""
        if not self.window:
            return
        from AppKit import NSApp

        NSApp().performSelector(
            self._draw_frame,
            withObject=None,
            afterDelay=1.0 / 30.0,
        )

    def _draw_frame(self) -> None:
        """Core frame update and render."""
        now = time.monotonic()
        dt = now - self._last_frame_time
        self._last_frame_time = now
        self._frame_count += 1

        # Smooth audio level interpolation
        lerp_speed = min(dt * 4.0, 1.0)
        self._audio_level = (
            self._audio_level + (self._target_level - self._audio_level) * lerp_speed
        )

        # Fade animation
        fade_speed = min(dt * 5.0, 1.0)
        if self._current_fade < self._fade_target:
            self._current_fade = min(self._current_fade + fade_speed, self._fade_target)
        elif self._current_fade > self._fade_target:
            self._current_fade = max(self._current_fade - fade_speed, self._fade_target)

        # Rotate spikes slowly
        self._spike_phase += dt * 0.3

        # Trigger redraw
        self.needsDisplay = True

        # Continue loop if visible
        if self._current_fade > 0.01:
            self._schedule_next_frame()

    # -- NSView drawRect --

    def drawRect_(self, rect: Any) -> None:
        """Render the ferrofluid sphere."""
        from AppKit import NSApplication

        if self._current_fade < 0.01:
            return

        ctx = NSApplication.sharedApplication().graphicsContext
        if ctx is None:
            return

        frame = self.frame()
        w = frame.size.width
        h = frame.size.height
        cx = w / 2.0
        cy = h / 2.0

        # Save context state
        ctx.saveGraphicsState()

        # Clear background
        ctx.setRGBFillColor(0.05, 0.05, 0.07, 1.0)
        ctx.fillRect_(((0, 0), (w, h)))

        # Apply fade
        alpha = self._current_fade * 0.9
        ctx.setAlpha(alpha)

        # Translate to sphere center
        ctx.beginPath()
        ctx.closePath()

        # Draw ambient glow (large radial gradient)
        glow_ctx = ctx
        glow_ctx.beginPath()
        glow = glow_ctx.createRadialGradient(
            (cx, cy), self._sphere_radius * 0.5,
            (cx, cy), self._sphere_radius * 3.0
        )
        glow.addColorStop(0.0, (0.15, 0.10, 0.25, 0.3))
        glow.addColorStop(0.5, (0.08, 0.05, 0.15, 0.1))
        glow.addColorStop(1.0, (0.0, 0.0, 0.0, 0.0))
        glow_ctx.saveGraphicsState()
        glow_ctx.clipToRect_(((0, 0), (w, h)))
        glow_ctx.fillRect_(((0, 0), (w, h)))
        glow_ctx.restoreGraphicsState()

        # Draw spikes
        self._draw_spikes(ctx, cx, cy)

        # Draw sphere base
        self._draw_sphere(ctx, cx, cy)

        # Draw specular highlight
        self._draw_highlight(ctx, cx, cy)

        ctx.restoreGraphicsState()

    def _draw_spikes(self, ctx: Any, cx: float, cy: float) -> None:
        """Draw ferrofluid spikes radiating from the sphere."""
        level = self._audio_level
        if level < 0.01:
            return

        # Audio-reactive intensity (non-linear for dramatic effect)
        intensity = min(level ** 0.7, 1.0)

        for i in range(self._spike_count):
            angle = (2.0 * math.pi * i / self._spike_count) + self._spike_phase
            # Base spike height with audio reactivity
            base_height = self._sphere_radius * 0.3
            spike_height = base_height + (self._max_spike_height - base_height) * intensity

            # Add organic variation per spike
            variation = math.sin(i * 1.7 + self._spike_phase * 0.5) * 0.3
            spike_height *= (1.0 + variation * intensity)

            # Calculate spike endpoints
            inner_x = cx + math.cos(angle) * (self._sphere_radius - 3.0)
            inner_y = cy + math.sin(angle) * (self._sphere_radius - 3.0)
            outer_x = cx + math.cos(angle) * (self._sphere_radius + spike_height)
            outer_y = cy + math.sin(angle) * (self._sphere_radius + spike_height)

            # Spike width (narrower at higher levels for sharper look)
            width = 3.0 - intensity * 1.5

            # Draw spike as a filled path
            perp_angle = angle + math.pi / 2
            half_w = width / 2.0
            p1x = inner_x + math.cos(perp_angle) * half_w
            p1y = inner_y + math.sin(perp_angle) * half_w
            p2x = outer_x + math.cos(perp_angle) * (half_w * 0.3)
            p2y = outer_y + math.sin(perp_angle) * (half_w * 0.3)
            p3x = outer_x - math.cos(perp_angle) * (half_w * 0.3)
            p3y = outer_y - math.sin(perp_angle) * (half_w * 0.3)
            p4x = inner_x - math.cos(perp_angle) * half_w
            p4y = inner_y - math.sin(perp_angle) * half_w

            # Spike color: deep purple with blue tint, darker at base
            r = 0.12 + intensity * 0.08
            g = 0.05 + intensity * 0.04
            b = 0.25 + intensity * 0.15

            ctx.beginPath()
            ctx.moveToPoint_((p1x, p1y))
            ctx.lineToPoint_((p2x, p2y))
            ctx.lineToPoint_((p3x, p3y))
            ctx.lineToPoint_((p4x, p4y))
            ctx.closePath()

            # Gradient fill for spike
            spike_grad = ctx.createLinearGradient(
                (inner_x, inner_y),
                (outer_x, outer_y)
            )
            spike_grad.addColorStop(0.0, (r * 0.5, g * 0.5, b * 0.5, 0.9))
            spike_grad.addColorStop(0.6, (r, g, b, 0.85))
            spike_grad.addColorStop(1.0, (r * 1.5, g * 1.2, b * 1.3, 0.3))
            ctx.setFillWithGradient_(spike_grad)
            ctx.fillPath()

    def _draw_sphere(self, ctx: Any, cx: float, cy: float) -> None:
        """Draw the main ferrofluid sphere with radial gradient."""
        r = self._sphere_radius

        # Sphere gradient: dark purple center to near-black edge
        sphere_grad = ctx.createRadialGradient(
            (cx - r * 0.2, cy - r * 0.2),
            r * 0.1,
            (cx, cy),
            r * 0.95
        )
        sphere_grad.addColorStop(0.0, (0.18, 0.12, 0.30, 1.0))
        sphere_grad.addColorStop(0.3, (0.12, 0.08, 0.22, 1.0))
        sphere_grad.addColorStop(0.7, (0.06, 0.04, 0.14, 1.0))
        sphere_grad.addColorStop(1.0, (0.03, 0.02, 0.08, 1.0))

        ctx.beginPath()
        ctx.addArc((cx, cy), r, 0, math.pi * 2, False)
        ctx.closePath()
        ctx.setFillWithGradient_(sphere_grad)
        ctx.fillPath()

        # Subtle surface undulation based on audio level
        level = self._audio_level
        if level > 0.01:
            undulation = level * 0.15
            surface_grad = ctx.createRadialGradient(
                (cx, cy), r * (1.0 - undulation),
                (cx, cy), r * (1.0 + undulation)
            )
            surface_grad.addColorStop(0.0, (0.0, 0.0, 0.0, 0.0))
            surface_grad.addColorStop(0.8, (0.15, 0.10, 0.25, 0.0))
            surface_grad.addColorStop(1.0, (0.20, 0.15, 0.35, level * 0.3))
            ctx.beginPath()
            ctx.addArc((cx, cy), r * (1.0 + undulation), 0, math.pi * 2, False)
            ctx.closePath()
            ctx.setFillWithGradient_(surface_grad)
            ctx.fillPath()

    def _draw_highlight(self, ctx: Any, cx: float, cy: float) -> None:
        """Draw specular highlight on the sphere."""
        highlight_r = self._sphere_radius * 0.35
        highlight_x = cx - self._sphere_radius * 0.25
        highlight_y = cy - self._sphere_radius * 0.25

        hl_grad = ctx.createRadialGradient(
            (highlight_x, highlight_y),
            0,
            (highlight_x, highlight_y),
            highlight_r
        )
        hl_grad.addColorStop(0.0, (0.45, 0.35, 0.60, 0.35))
        hl_grad.addColorStop(0.4, (0.25, 0.18, 0.40, 0.15))
        hl_grad.addColorStop(1.0, (0.10, 0.06, 0.20, 0.0))

        ctx.beginPath()
        ctx.addArc((highlight_x, highlight_y), highlight_r, 0, math.pi * 2, False)
        ctx.closePath()
        ctx.setFillWithGradient_(hl_grad)
        ctx.fillPath()

        # Secondary blue highlight
        blue_x = cx + self._sphere_radius * 0.3
        blue_y = cy + self._sphere_radius * 0.15
        blue_r = self._sphere_radius * 0.2

        blue_grad = ctx.createRadialGradient(
            (blue_x, blue_y),
            0,
            (blue_x, blue_y),
            blue_r
        )
        blue_grad.addColorStop(0.0, (0.10, 0.15, 0.35, 0.15))
        blue_grad.addColorStop(1.0, (0.05, 0.08, 0.20, 0.0))

        ctx.beginPath()
        ctx.addArc((blue_x, blue_y), blue_r, 0, math.pi * 2, False)
        ctx.closePath()
        ctx.setFillWithGradient_(blue_grad)
        ctx.fillPath()
