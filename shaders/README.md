# BSL-Style Shader Pack for Minecraft Clone

A comprehensive deferred rendering shader pack inspired by the popular BSL (Beautiful Shaders Lite) shaders, designed for OptiFine-compatible deferred rendering pipelines.

## Features

### Core Rendering Pipeline
- **Full Deferred Rendering**: Implements the complete stage order: shadow → shadow_composite → prepare → gbuffers → deferred → translucent → composite → final
- **Ping-Pong Buffers**: Uses colortex0-15 with alternating buffers to prevent read-after-write hazards
- **Multiple Graphics Presets**: Low, Medium, High, and Ultra quality settings

### Shadows & Lighting
- **Real-time Dynamic Shadows**: Configurable shadow map resolution (512/1024/2048/4096)
- **PCF Soft Shadows**: Percentage-Closer Filtering with configurable kernel size
- **Volumetric Lighting**: Godrays sampled along camera rays through shadow map
- **Time-based Sky Color**: Dynamic skylight from dawn pastels to noon warmth to dusk oranges

### Water Effects
- **Screen Space Reflections (SSR)**: Mirrors adjacent terrain and clouds
- **Multi-bounce Reflections**: Physically plausible water reflections (configurable 0-2 bounces)
- **Wave Distortion**: Vertex displacement with multi-frequency wave simulation
- **Refraction**: Shoreline visibility with distorted underwater view
- **Foam Generation**: Depth-based foam at shorelines

### Sky & Atmosphere
- **Procedural Clouds**: FBM noise-based volumetric-style clouds
- **Time-based Cloud Coloring**: Dawn/dusk orange-pink tints, night darkening
- **Weather Integration**: Rain/thunder affect cloud density and lighting
- **Biome-specific Fog**: Different fog colors for desert, taiga, swamp biomes

### Post-Processing & Color Grading
- **Time-based Color Grading**: 
  - Dawn: Cool pastels
  - Noon: Warm saturation boost
  - Dusk: Orange tones
  - Night: Cool blue tint
- **Bloom**: Multi-pass Gaussian blur on highlights
- **TAA (Temporal Anti-Aliasing)**: Reprojects previous frame with motion vectors
- **FXAA**: Fast approximate anti-aliasing for edge smoothing
- **Depth of Field**: Configurable focus distance and aperture
- **Motion Blur**: Optional cinematic motion blur
- **Film Grain & Vignette**: Subtle cinematic effects

### Advanced Materials
- **Parallax Occlusion Mapping (POM)**: Depth-based texture displacement
- **Normal Mapping**: Tangent space normals for detailed surfaces
- **Specular/Gloss Maps**: Material properties per surface

### Customization Options
- Cel-shading toggle
- World curvature effect
- Outline rendering
- Leaves/grass sway animation
- Dynamic torch lighting with flicker

## File Structure

```
shaders/
├── pipeline_config.glsl      # Shared uniforms, constants, and macros
├── shadow/
│   ├── shadow.vsh            # Shadow map generation (vertex)
│   └── shadow.fsh            # Shadow map generation (fragment)
├── gbuffers/
│   ├── gbuffers_terrain.vsh  # Terrain geometry pass (vertex)
│   ├── gbuffers_terrain.fsh  # Terrain geometry pass (fragment)
│   ├── gbuffers_cloud.vsh    # Cloud rendering (vertex)
│   └── gbuffers_cloud.fsh    # Cloud rendering (fragment)
├── deferred/
│   ├── deferred.vsh          # Lighting calculation (vertex)
│   └── deferred.fsh          # Lighting calculation (fragment)
├── translucent/
│   ├── water.vsh             # Water rendering (vertex)
│   └── water.fsh             # Water rendering (fragment)
├── composite/
│   └── composite.fsh         # Post-processing and color grading
└── final/
    ├── final.vsh             # Final output pass (vertex)
    └── final.fsh             # TAA, FXAA, and final tone mapping
```

## Color Attachments (colortex0-15)

| Buffer | Purpose | Ping-Pong Pair |
|--------|---------|----------------|
| colortex0 | Albedo/Color | colortex8 |
| colortex1 | Specular/Gloss | colortex9 |
| colortex2 | Normals (RGB encoded) | - |
| colortex3 | Depth/Distance | - |
| colortex4 | Shadow sample buffer | - |
| colortex5 | Volumetric light | - |
| colortex6 | SSR reflections | - |
| colortex7 | Bloom highlights | - |
| colortex10 | Previous frame (TAA) | - |
| colortex11 | Motion vectors | - |
| colortex12 | LUT/Color grading temp | - |
| colortex13 | Clouds overlay | - |
| colortex14 | Water mask/refraction | - |
| colortex15 | Utility buffer | - |

## Performance Considerations

### Quality Presets
- **Low**: 512px shadows, no SSR, simplified PCF, no POM
- **Medium**: 1024px shadows, single-bounce SSR, basic PCF
- **High**: 2048px shadows, multi-bounce SSR, full PCF, POM enabled
- **Ultra**: 4096px shadows, advanced SSR, enhanced effects

### Optimization Techniques
- Exponential raymarch step growth for SSR performance
- Configurable shadow update rates based on quality
- Buffer downscaling options for expensive effects
- Modular code allowing individual effect toggles
- Early fragment discard for transparent surfaces

## Integration Guide

### 1. Include Pipeline Configuration
```glsl
#include "/pipeline_config.glsl"
```

### 2. Set Up Framebuffers
Create FBOs for each stage with appropriate color attachments:
```cpp
// Example OpenGL setup
GLuint gbufferFBO;
glGenFramebuffers(1, &gbufferFBO);
glBindFramebuffer(GL_FRAMEBUFFER, gbufferFBO);

// Attach colortex0-7 for GBuffer outputs
glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, colortex0, 0);
glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT1, GL_TEXTURE_2D, colortex1, 0);
// ... etc
```

### 3. Render Stage Order
```cpp
// 1. Shadow Pass
renderShadowMap();

// 2. GBuffer Pass (geometry)
renderGBuffers();

// 3. Deferred Lighting
renderDeferredLighting();

// 4. Translucent Objects (water, etc.)
renderTranslucent();

// 5. Composite (post-processing)
renderComposite();

// 6. Final Pass (TAA/FXAA)
renderFinal();
```

### 4. Uniform Setup
Set all required uniforms before each draw call. Key uniforms include:
- `gameTime`: Current time in hours (0-24)
- `skyLight`: Sky brightness (0-1)
- `cameraPosition`: Player/camera world position
- `shadowMatrix`: Bias * lightProjection * lightView
- `screenSize`: Window dimensions
- `texelSize`: 1.0 / screenSize

## Requirements

- OpenGL 3.3 Core or higher
- Support for multiple render targets (MRT)
- Floating-point texture support
- Shadow sampler support

## Credits

Inspired by:
- **BSL Shaders** by Capt Tatsu
- **OptiFine** by sp614x
- Original Minecraft lighting implementation in this project

## License

MIT License - See LICENSE file for details
