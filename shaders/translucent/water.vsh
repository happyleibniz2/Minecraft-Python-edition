// Translucent Water Vertex Shader - BSL Style SSR Water
#version 330 core

#include "/pipeline_config.glsl"

// Input attributes
layout(location = 0) in vec3 inPosition;
layout(location = 1) in vec2 inTexCoord;
layout(location = 2) in vec4 inColor;

// Uniforms
uniform mat4 projectionMatrix;
uniform mat4 viewMatrix;
uniform mat4 modelMatrix;
uniform float gameTime;
uniform int ssrEnabled;
uniform int ssrBounces;

// Outputs to fragment shader
out vec3 outWorldPos;
out vec2 outTexCoord;
out vec4 outColor;
out vec3 outNormal;
out vec4 outShadowCoord;

void main() {
    // Apply wave displacement to vertices
    vec3 displacedPosition = inPosition;
    
    // Multi-frequency wave simulation for realistic water surface
    float time = gameTime * 0.5;
    float wave1 = sin(inPosition.x * 0.5 + time) * 0.15;
    float wave2 = cos(inPosition.z * 0.3 + time * 0.8) * 0.1;
    float wave3 = sin((inPosition.x + inPosition.z) * 0.2 + time * 1.2) * 0.05;
    
    displacedPosition.y += wave1 + wave2 + wave3;
    
    // Calculate world position
    vec4 worldPos = modelMatrix * vec4(displacedPosition, 1.0);
    outWorldPos = worldPos.xyz;
    
    // Water surface normal (affected by waves)
    float epsilon = 0.01;
    float hL = wave1 + wave2 + wave3;
    float hR = sin((displacedPosition.x + epsilon) * 0.5 + time) * 0.15 
               + cos(displacedPosition.z * 0.3 + time * 0.8) * 0.1
               + sin((displacedPosition.x + epsilon + displacedPosition.z) * 0.2 + time * 1.2) * 0.05;
    float hU = sin((displacedPosition.x) * 0.5 + time) * 0.15 
               + cos((displacedPosition.z + epsilon) * 0.3 + time * 0.8) * 0.1
               + sin((displacedPosition.x + displacedPosition.z + epsilon) * 0.2 + time * 1.2) * 0.05;
    
    vec3 normal = normalize(vec3(hL - hR, epsilon, hL - hU));
    outNormal = normal;
    
    // Pass through data
    outTexCoord = inTexCoord;
    outColor = inColor;
    
    // Shadow coordinates (would need shadowMatrix uniform in full implementation)
    outShadowCoord = vec4(0.0);
    
    // Final clip-space position
    vec4 viewPos = viewMatrix * worldPos;
    gl_Position = projectionMatrix * viewPos;
}
