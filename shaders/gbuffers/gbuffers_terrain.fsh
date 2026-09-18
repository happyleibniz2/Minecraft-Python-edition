// GBuffers Terrain Fragment Shader - BSL Style Deferred Rendering
// Writes to multiple color attachments for deferred lighting pipeline
#version 330 core

#include "/pipeline_config.glsl"

// Inputs from vertex shader
in vec3 inWorldPos;
in vec3 inNormal;
in vec4 inColor;
in vec2 inTexCoord;
in float inTorchLight;
in vec4 inShadowCoord;
in float inFogDistance;

// Uniforms
uniform sampler2D texture0;          // Main block texture
uniform float gameTime;
uniform int parallaxMappingEnabled;
uniform float parallaxDepth;
uniform int renderQuality;

// GBuffer Outputs (matching OptiFine colortex convention)
layout(location = 0) out vec4 colortex0;  // Albedo/Color
layout(location = 1) out vec4 colortex1;  // Specular/Gloss
layout(location = 2) out vec4 colortex2;  // Normals (RGB encoded)
layout(location = 3) out vec4 colortex3;  // Depth/Distance
layout(location = 4) out vec4 colortex4;  // Shadow sample buffer (optional)
layout(location = 5) out vec4 colortex5;  // Volumetric light accumulator
layout(location = 6) out vec4 colortex6;  // SSR reflection buffer
layout(location = 7) out vec4 colortex7;  // Bloom/highlight buffer

void main() {
    // Sample base texture
    vec4 texel = texture(texture0, inTexCoord);
    
    // Parallax Occlusion Mapping (POM) for advanced materials
    if (parallaxMappingEnabled == 1 && renderQuality >= QUALITY_HIGH) {
        // Simplified POM - in full implementation, would iterate depth map
        vec2 viewDir = normalize(inWorldPos - cameraPosition);
        float parallaxOffset = dot(viewDir, inNormal) * parallaxDepth * inTorchLight;
        vec2 pomTexCoord = inTexCoord + viewDir.xy * parallaxOffset;
        texel = texture(texture0, clamp(pomTexCoord, 0.0, 1.0));
    }
    
    // Apply vertex color
    vec4 finalColor = texel * inColor;
    
    // Discard transparent fragments (alpha test like original shader)
    if (finalColor.a < 0.5) {
        discard;
    }
    
    // Encode normal as RGB (BSL style: tangent space normals)
    vec3 encodedNormal = inNormal * 0.5 + 0.5;  // Convert from [-1,1] to [0,1]
    
    // Calculate specular/gloss values (material properties)
    // In full implementation, these would come from material textures
    float specular = 0.0;
    float gloss = 0.5;
    
    // Check for water-like surfaces
    if (texel.b > 0.8 && texel.r < 0.3) {  // Simple blue detection for water
        specular = 0.3;
        gloss = 0.8;
    }
    
    // Calculate bloom threshold (bright areas for bloom effect)
    float luminance = dot(finalColor.rgb, vec3(0.2126, 0.7152, 0.0722));
    vec3 bloom = max(vec3(0.0), finalColor.rgb - vec3(0.8));
    
    // Output to GBuffer attachments
    colortex0 = finalColor;                          // Albedo
    colortex1 = vec4(specular, gloss, 0.0, 1.0);     // Material properties
    colortex2 = vec4(encodedNormal, 1.0);            // Normals
    colortex3 = vec4(inFogDistance / 256.0, 0.0, 0.0, 1.0);  // Depth (normalized)
    colortex4 = vec4(0.0);                           // Reserved for shadow sampling
    colortex5 = vec4(0.0);                           // Will be filled by deferred stage
    colortex6 = vec4(0.0);                           // Will be filled by SSR pass
    colortex7 = vec4(bloom, 1.0);                    // Bloom highlights
}
