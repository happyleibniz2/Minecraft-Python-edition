// Shadow Map Vertex Shader - BSL Style
#version 330 core

#include "/pipeline_config.glsl"

// Input attributes
layout(location = 0) in vec3 inPosition;
layout(location = 1) in vec2 inTexCoord;
layout(location = 2) in float inSwayWeight;  // For leaves/grass animation

// Uniforms
uniform mat4 shadowProjectionMatrix;
uniform mat4 shadowViewMatrix;
uniform mat4 modelMatrix;
uniform float gameTime;
uniform vec2 cloudOffset;
uniform float leavesSway;

// Output to fragment shader (depth only, but pass for debugging)
out float outDepth;
out vec3 outWorldPos;

void main() {
    vec3 animatedPosition = inPosition;
    
    // Leaf and grass sway animation (same as original Light.py shader)
    if (leavesSway > 0.5 && inSwayWeight > 0.0) {
        float primary = sin(gameTime * 1.65 
            + inPosition.x * 0.73 + inPosition.z * 0.51 + cloudOffset.x * 0.035);
        float detail = sin(gameTime * 2.47 
            + inPosition.x * 1.31 - inPosition.z * 0.87 + cloudOffset.y * 0.05);
        float motion = (primary * 0.72 + detail * 0.28) * inSwayWeight;
        animatedPosition.x += motion * 0.075;
        animatedPosition.z += motion * 0.032;
    }
    
    // World position for debugging/advanced effects
    vec4 worldPos = modelMatrix * vec4(animatedPosition, 1.0);
    outWorldPos = worldPos.xyz;
    
    // Transform to shadow light's view space
    vec4 shadowSpacePos = shadowProjectionMatrix * shadowViewMatrix * vec4(animatedPosition, 1.0);
    
    gl_Position = shadowSpacePos;
    outDepth = shadowSpacePos.z / shadowSpacePos.w;
}
