"""
GLSL Shader Programs for the OpenGL renderer.

Provides minimal, high-performance shaders for rendering iPhone
screen frames as textured quads with proper aspect ratio.

The pipeline:
  CPU frame buffer → glTexSubImage2D → GPU texture → fragment shader → display
"""

# Vertex shader: Renders a fullscreen quad with texture coordinates
VERTEX_SHADER = """
#version 330 core

layout(location = 0) in vec2 aPosition;
layout(location = 1) in vec2 aTexCoord;

out vec2 vTexCoord;

uniform mat4 uProjection;

void main() {
    gl_Position = uProjection * vec4(aPosition, 0.0, 1.0);
    vTexCoord = aTexCoord;
}
"""

# Fragment shader: Samples the texture and outputs the pixel color
FRAGMENT_SHADER = """
#version 330 core

in vec2 vTexCoord;
out vec4 FragColor;

uniform sampler2D uTexture;

void main() {
    FragColor = texture(uTexture, vTexCoord);
}
"""

# Fragment shader with brightness/contrast adjustment (optional)
FRAGMENT_SHADER_ENHANCED = """
#version 330 core

in vec2 vTexCoord;
out vec4 FragColor;

uniform sampler2D uTexture;
uniform float uBrightness;  // 0.0 = normal
uniform float uContrast;    // 1.0 = normal

void main() {
    vec4 color = texture(uTexture, vTexCoord);

    // Apply contrast
    color.rgb = (color.rgb - 0.5) * uContrast + 0.5;

    // Apply brightness
    color.rgb += uBrightness;

    // Clamp
    color.rgb = clamp(color.rgb, 0.0, 1.0);

    FragColor = color;
}
"""


def get_fullscreen_quad_vertices(
    aspect_ratio: float,
    viewport_width: int,
    viewport_height: int,
) -> list[float]:
    """Calculate vertex positions for aspect-ratio-preserving quad.

    Returns vertices as [x, y, u, v, ...] for 6 vertices (2 triangles).
    The quad is sized to fit within the viewport while preserving the
    source aspect ratio (letterboxing or pillarboxing as needed).

    Args:
        aspect_ratio: Source width / height
        viewport_width: Window width in pixels
        viewport_height: Window height in pixels

    Returns:
        List of 24 floats: 6 vertices × (x, y, u, v)
    """
    viewport_aspect = viewport_width / max(viewport_height, 1)

    if aspect_ratio > viewport_aspect:
        # Source is wider → pillarbox (black bars top/bottom)
        w = 1.0
        h = viewport_aspect / aspect_ratio
    else:
        # Source is taller → letterbox (black bars left/right)
        w = aspect_ratio / viewport_aspect
        h = 1.0

    # Quad vertices in NDC (-1 to 1), with texture coords (0 to 1)
    # Two triangles forming a quad
    return [
        # Triangle 1
        -w, -h,   0.0, 1.0,   # bottom-left  (tex flipped Y)
         w, -h,   1.0, 1.0,   # bottom-right
         w,  h,   1.0, 0.0,   # top-right

        # Triangle 2
        -w, -h,   0.0, 1.0,   # bottom-left
         w,  h,   1.0, 0.0,   # top-right
        -w,  h,   0.0, 0.0,   # top-left
    ]
