// Cloud Vertex Shader - BSL Style Atmosphere
#version 330 core

#include "/pipeline_config.glsl"

// Input attributes
layout(location = 0) in vec3 inPosition;
layout(location = 1) in vec2 inTexCoord;

// Uniforms
uniform mat4 projectionMatrix;
uniform mat4 viewMatrix;
uniform mat4 modelMatrix;
uniform vec2 cloudOffset;
uniform float gameTime;

// Outputs
out vec2 outTexCoord;
out vec3 outWorldPos;
out float outCloudDensity;

void main() {
    // Animate cloud position over time
    vec3 animatedPosition = inPosition;
    animatedPosition.x += cloudOffset.x * 50.0;
    animatedPosition.z += cloudOffset.y * 50.0;
    
    // Calculate world position
    vec4 worldPos = modelMatrix * vec4(animatedPosition, 1.0);
    outWorldPos = worldPos.xyz;
    
    // Pass through texture coordinates
    outTexCoord = inTexCoord;
    
    // Calculate cloud density based on noise (will be computed in fragment shader)
    outCloudDensity = 0.0;
    
    // Final clip-space position
    vec4 viewPos = viewMatrix * worldPos;
    gl_Position = projectionMatrix * viewPos;
}
