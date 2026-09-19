// Shadow Map Fragment Shader - BSL Style
// Generates depth-only shadow map with PCF-ready precision
#version 330 core

#include "/pipeline_config.glsl"

// Input from vertex shader
in float inDepth;
in vec3 inWorldPos;

// Output: single depth value to shadow texture (colortex4 or depth attachment)
layout(location = 0) out float fragDepth;

// Uniforms for advanced culling
uniform float shadowDistance;
uniform vec3 lightDirection;

void main() {
    // Standard depth output for shadow mapping
    fragDepth = inDepth;
    
    // Optional: discard fragments beyond shadow distance for performance
    // float distFromLight = length(inWorldPos);
    // if (distFromLight > shadowDistance) discard;
}
