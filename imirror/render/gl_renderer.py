"""
OpenGL Renderer — GPU-accelerated frame display.

Renders captured iPhone frames as textured quads using OpenGL 3.3.
Designed for minimal latency:

- Zero-copy texture upload (glTexSubImage2D directly from numpy buffer)
- VSync-locked swap for tear-free display
- Aspect-ratio preserving letterbox/pillarbox
- Smooth resize handling
- Cached quad vertices (only recalculated on aspect ratio or viewport change)
"""

import logging
import ctypes
import time
from typing import Optional

import numpy as np

from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QSurfaceFormat

from imirror.render.shaders import (
    VERTEX_SHADER, FRAGMENT_SHADER,
    get_fullscreen_quad_vertices,
)
from imirror.config import config

logger = logging.getLogger(__name__)

# Try to import OpenGL
try:
    from OpenGL.GL import (
        glGenTextures, glBindTexture, glTexImage2D, glTexSubImage2D,
        glTexParameteri, glEnable, glDisable, glClear, glClearColor,
        glViewport, glDrawArrays, glUseProgram, glGetUniformLocation,
        glUniform1i, glUniformMatrix4fv, glActiveTexture,
        glGenVertexArrays, glBindVertexArray, glGenBuffers,
        glBindBuffer, glBufferData, glBufferSubData,
        glVertexAttribPointer, glEnableVertexAttribArray,
        glCreateShader, glShaderSource, glCompileShader,
        glGetShaderiv, glGetShaderInfoLog, glCreateProgram,
        glAttachShader, glLinkProgram, glGetProgramiv,
        glGetProgramInfoLog, glDeleteShader,
        GL_TEXTURE_2D, GL_TEXTURE0, GL_RGB, GL_UNSIGNED_BYTE,
        GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER,
        GL_LINEAR, GL_NEAREST, GL_CLAMP_TO_EDGE,
        GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T,
        GL_COLOR_BUFFER_BIT, GL_TRIANGLES, GL_FLOAT,
        GL_ARRAY_BUFFER, GL_STATIC_DRAW, GL_DYNAMIC_DRAW,
        GL_VERTEX_SHADER, GL_FRAGMENT_SHADER,
        GL_COMPILE_STATUS, GL_LINK_STATUS, GL_FALSE, GL_TRUE,
    )
    OPENGL_AVAILABLE = True
except ImportError:
    OPENGL_AVAILABLE = False
    logger.warning("PyOpenGL not available — rendering disabled")


class GLRenderer(QOpenGLWidget):
    """
    OpenGL widget that renders iPhone screen frames.

    Receives numpy arrays (H, W, 3) from the capture backend and
    uploads them as GPU textures for rendering. Handles aspect ratio
    preservation and smooth resizing.
    """

    def __init__(self, parent=None):
        # Set up OpenGL format before creating widget
        fmt = QSurfaceFormat()
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        fmt.setSwapBehavior(QSurfaceFormat.SwapBehavior.DoubleBuffer)
        if config.vsync:
            fmt.setSwapInterval(1)
        else:
            fmt.setSwapInterval(0)
        QSurfaceFormat.setDefaultFormat(fmt)

        super().__init__(parent)

        # OpenGL objects
        self._texture_id: int = 0
        self._vao: int = 0
        self._vbo: int = 0
        self._program: int = 0

        # Frame state (what the capture backend has sent us)
        self._current_frame: Optional[np.ndarray] = None
        self._frame_width: int = 0
        self._frame_height: int = 0
        self._needs_upload: bool = False

        # Texture state (what the GPU texture is currently allocated as)
        self._texture_initialized: bool = False
        self._texture_width: int = 0
        self._texture_height: int = 0

        # Quad vertex cache — only recalculate when viewport or aspect changes
        self._cached_aspect: float = 0.0
        self._cached_vp_w: int = 0
        self._cached_vp_h: int = 0
        self._vertices_dirty: bool = True

        # Performance
        self._render_count: int = 0
        self._last_render_time: float = 0

        # Refresh timer — trigger repaint when new frames might be ready
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(2)  # ~500Hz poll rate, VSync limits actual draws

    def set_frame(self, pixels: np.ndarray, width: int, height: int) -> None:
        """Update the frame to render.

        Called from the UI thread (via Qt signal). We store the reference
        and flag for upload on the next paint event.
        """
        self._current_frame = pixels
        self._frame_width = width
        self._frame_height = height
        self._needs_upload = True

    # ─── OpenGL lifecycle ───────────────────────────────────────────

    def initializeGL(self) -> None:
        """Initialize OpenGL resources."""
        if not OPENGL_AVAILABLE:
            return

        logger.info("Initializing OpenGL renderer...")

        glClearColor(0.05, 0.05, 0.05, 1.0)  # Near-black background

        # Compile shaders and create program
        self._program = self._create_shader_program(
            VERTEX_SHADER, FRAGMENT_SHADER
        )

        # Create VAO and VBO
        self._vao = glGenVertexArrays(1)
        self._vbo = glGenBuffers(1)

        glBindVertexArray(self._vao)
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo)

        # Allocate buffer for 6 vertices × 4 floats
        glBufferData(GL_ARRAY_BUFFER, 6 * 4 * 4, None, GL_DYNAMIC_DRAW)

        # Position attribute (location 0)
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 4 * 4, ctypes.c_void_p(0))
        glEnableVertexAttribArray(0)

        # TexCoord attribute (location 1)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 4 * 4, ctypes.c_void_p(2 * 4))
        glEnableVertexAttribArray(1)

        glBindVertexArray(0)

        # Create texture
        self._texture_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self._texture_id)

        # Texture filtering
        filter_mode = GL_LINEAR if config.render_interpolation == "linear" else GL_NEAREST
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, filter_mode)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, filter_mode)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

        logger.info("OpenGL renderer initialized")

    def resizeGL(self, width: int, height: int) -> None:
        """Handle window resize."""
        if not OPENGL_AVAILABLE:
            return
        glViewport(0, 0, width, height)
        self._vertices_dirty = True  # Force vertex recalculation

    def paintGL(self) -> None:
        """Render the current frame."""
        if not OPENGL_AVAILABLE:
            return

        glClear(GL_COLOR_BUFFER_BIT)

        if self._current_frame is None:
            return

        # Upload new frame to GPU texture if needed
        if self._needs_upload:
            self._upload_texture()
            self._needs_upload = False

        # Update quad vertices only when aspect ratio or viewport changes
        self._update_quad_vertices()

        # Draw
        glUseProgram(self._program)

        # Set texture uniform
        tex_loc = glGetUniformLocation(self._program, "uTexture")
        glUniform1i(tex_loc, 0)

        # Set projection (identity — we compute NDC in vertex data)
        proj_loc = glGetUniformLocation(self._program, "uProjection")
        identity = np.eye(4, dtype=np.float32)
        glUniformMatrix4fv(proj_loc, 1, GL_FALSE, identity)

        # Bind texture
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self._texture_id)

        # Draw quad
        glBindVertexArray(self._vao)
        glDrawArrays(GL_TRIANGLES, 0, 6)
        glBindVertexArray(0)

        self._render_count += 1
        self._last_render_time = time.monotonic()

    # ─── Internal helpers ───────────────────────────────────────────

    def _upload_texture(self) -> None:
        """Upload the current frame to the GPU texture.

        Tracks the texture's allocated dimensions separately from the
        incoming frame dimensions. When the device rotates (e.g. portrait
        → landscape), the texture is reallocated to match the new size.
        """
        frame = self._current_frame
        if frame is None:
            return

        h, w = frame.shape[:2]

        glBindTexture(GL_TEXTURE_2D, self._texture_id)

        # Reallocate texture if first upload OR dimensions changed
        if (not self._texture_initialized
                or w != self._texture_width
                or h != self._texture_height):
            glTexImage2D(
                GL_TEXTURE_2D, 0, GL_RGB,
                w, h, 0,
                GL_RGB, GL_UNSIGNED_BYTE,
                frame,  # zero-copy: numpy buffer passed directly to GPU
            )
            self._texture_initialized = True
            self._texture_width = w
            self._texture_height = h
            self._vertices_dirty = True  # Aspect ratio may have changed
            logger.debug("Texture (re)allocated: %dx%d", w, h)
        else:
            # Fast sub-image update (no reallocation needed)
            glTexSubImage2D(
                GL_TEXTURE_2D, 0,
                0, 0, w, h,
                GL_RGB, GL_UNSIGNED_BYTE,
                frame,  # zero-copy: numpy buffer passed directly to GPU
            )

    def _update_quad_vertices(self) -> None:
        """Recalculate quad vertices only when aspect ratio or viewport changes.

        Caches the result to avoid per-frame recalculation overhead.
        """
        if self._frame_width == 0 or self._frame_height == 0:
            return

        aspect = self._frame_width / self._frame_height
        vp_w = self.width()
        vp_h = self.height()

        # Skip if nothing changed
        if (not self._vertices_dirty
                and aspect == self._cached_aspect
                and vp_w == self._cached_vp_w
                and vp_h == self._cached_vp_h):
            return

        vertices = get_fullscreen_quad_vertices(aspect, vp_w, vp_h)
        vertex_data = np.array(vertices, dtype=np.float32)

        glBindBuffer(GL_ARRAY_BUFFER, self._vbo)
        glBufferSubData(GL_ARRAY_BUFFER, 0, vertex_data.nbytes, vertex_data)

        # Cache the values
        self._cached_aspect = aspect
        self._cached_vp_w = vp_w
        self._cached_vp_h = vp_h
        self._vertices_dirty = False

    def _create_shader_program(self, vert_src: str, frag_src: str) -> int:
        """Compile and link a shader program."""
        vert = self._compile_shader(vert_src, GL_VERTEX_SHADER)
        frag = self._compile_shader(frag_src, GL_FRAGMENT_SHADER)

        program = glCreateProgram()
        glAttachShader(program, vert)
        glAttachShader(program, frag)
        glLinkProgram(program)

        if glGetProgramiv(program, GL_LINK_STATUS) == GL_FALSE:
            error = glGetProgramInfoLog(program).decode()
            raise RuntimeError(f"Shader link error: {error}")

        glDeleteShader(vert)
        glDeleteShader(frag)

        return program

    def _compile_shader(self, source: str, shader_type: int) -> int:
        """Compile a single shader."""
        shader = glCreateShader(shader_type)
        glShaderSource(shader, source)
        glCompileShader(shader)

        if glGetShaderiv(shader, GL_COMPILE_STATUS) == GL_FALSE:
            error = glGetShaderInfoLog(shader).decode()
            type_name = "vertex" if shader_type == GL_VERTEX_SHADER else "fragment"
            raise RuntimeError(f"{type_name} shader compile error: {error}")

        return shader
