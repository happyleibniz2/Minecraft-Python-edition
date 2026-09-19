// BSL-Style Deferred Rendering Pipeline Configuration
// This file defines the complete rendering stage order for OptiFine-compatible deferred shading

/*
 * RENDERING PIPELINE STAGE ORDER:
 * 1. shadow        - Shadow map generation (depth only)
 * 2. shadow_composite - Post-shadow processing
 * 3. prepare       - Buffer preparation and clearing
 * 4. gbuffers      - Geometry buffer generation (color, normals, depth, etc.)
 * 5. deferred      - Lighting calculations using GBuffer data
 * 6. translucent   - Transparent object rendering with SSR
 * 7. composite     - Post-processing, bloom, color grading
 * 8. final         - Final output with TAA/FXAA
 *
 * COLOR ATTACHMENTS (colortex0-15):
 * colortex0  - Albedo/Color (ping-pong with colortex8)
 * colortex1  - Specular/Gloss (ping-pong with colortex9)
 * colortex2  - Normals (encoded as RGB)
 * colortex3  - Depth/Distance
 * colortex4  - Shadow map sample buffer
 * colortex5  - Volumetric light accumulation
 * colortex6  - SSR reflection buffer
 * colortex7  - Bloom/highlight buffer
 * colortex8  - Ping-pong for colortex0
 * colortex9  - Ping-pong for colortex1
 * colortex10 - Previous frame color (TAA)
 * colortex11 - Motion vectors
 * colortex12 - LUT/Color grading temp
 * colortex13 - Clouds overlay
 * colortex14 - Water mask/refraction
 * colortex15 - Temp/Utility
 */

// SHADER STAGE DEFINITIONS
const string SHADOW_STAGE = "shadow";
const string SHADOW_COMPOSITE_STAGE = "shadow_composite";
const string PREPARE_STAGE = "prepare";
const string GBUFFERS_STAGE = "gbuffers";
const string DEFERRED_STAGE = "deferred";
const string TRANSLUCENT_STAGE = "translucent";
const string COMPOSITE_STAGE = "composite";
const string FINAL_STAGE = "final";

// QUALITY PRESETS
const int QUALITY_LOW = 0;
const int QUALITY_MEDIUM = 1;
const int QUALITY_HIGH = 2;
const int QUALITY_ULTRA = 3;

// FEATURE TOGGLES (exposed to options menu)
uniform int renderQuality;           // 0=Low, 1=Medium, 2=High, 3=Ultra
uniform int shadowEnabled;           // 0=Off, 1=On
uniform int shadowMapResolution;     // 512, 1024, 2048, 4096
uniform int shadowSoftness;          // PCF kernel size
uniform int volumetricLightEnabled;  // Godrays on/off
uniform int ssrEnabled;              // Screen-space reflections
uniform int ssrBounces;              // 0-2 reflection bounces
uniform int bloomEnabled;            // Bloom effect
uniform int taaEnabled;              // Temporal anti-aliasing
uniform int fxaaEnabled;             // Fast approximate AA
uniform int dofEnabled;              // Depth of field
uniform int motionBlurEnabled;       // Motion blur
uniform int worldCurvatureEnabled;   // Vertex displacement
uniform int outlineEnabled;          // Cel-shading outlines
uniform int parallaxMappingEnabled;  // POM for materials

// TIME AND ENVIRONMENT
uniform float gameTime;              // 0.0-24.0 hours
uniform float sunAngle;              // Sun position in radians
uniform float rainStrength;          // 0.0-1.0
uniform float thunderStrength;       // 0.0-1.0
uniform int biomeType;               // Biome ID for fog/atmosphere

// CAMERA
uniform vec3 cameraPosition;
uniform vec3 cameraForward;
uniform vec3 cameraUp;
uniform vec3 cameraRight;
uniform mat4 projectionMatrix;
uniform mat4 viewMatrix;
uniform mat4 inverseViewMatrix;
uniform mat4 shadowMatrix;

// SCREEN
uniform vec2 screenSize;
uniform vec2 texelSize;              // 1.0 / screenSize
uniform float aspectRatio;
uniform float fov;

// PING-PONG BUFFER MANAGEMENT
// Alternates between pairs each frame to avoid read-after-write hazards
uniform int frameCounter;
uniform bool pingPongA;              // true = use even buffers, false = use odd

// Helper macros for buffer selection
#define GET_BUFFER(base, id) (pingPongA ? base##id : base##id##_alt)
#define SWITCH_BUFFER(base, id) (pingPongA ? base##id##_alt : base##id)
