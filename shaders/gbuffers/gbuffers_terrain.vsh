// GBuffers Terrain Vertex Shader - BSL Style Deferred Rendering
#version 330 core

#include "/pipeline_config.glsl"

// Input attributes (matching original Light.py shader layout)
layout(location = 0) in vec3 inPosition;
layout(location = 1) in vec2 inTexCoord;
layout(location = 2) in float inTorchLight;  // Encoded in texCoord.z originally
layout(location = 3) in vec4 inColor;
layout(location = 4) in float inSwayWeight;  // For leaves/grass

// Uniforms
uniform mat4 projectionMatrix;
uniform mat4 viewMatrix;
uniform mat4 modelMatrix;
uniform mat4 shadowMatrix;
uniform mat4 inverseViewMatrix;
uniform float gameTime;
uniform vec2 cloudOffset;
uniform float leavesSway;
uniform int worldCurvatureEnabled;

// Outputs to fragment shader (GBuffer data)
out vec3 outWorldPos;
out vec3 outNormal;
out vec4 outColor;
out vec2 outTexCoord;
out float outTorchLight;
out vec4 outShadowCoord;
out float outFogDistance;

void main() {
    vec3 animatedPosition = inPosition;
    
    // World curvature effect (optional, for cinematic look)
    if (worldCurvatureEnabled == 1) {
        vec3 centeredPos = inPosition;
        float curveAmount = 0.00002;  // Subtle curvature
        float curveOffset = dot(centeredPos.xy, centeredPos.xy) * curveAmount;
        animatedPosition.z -= curveOffset;
    }
    
    // Leaf and grass sway animation (consistent with original shader)
    if (leavesSway > 0.5 && inSwayWeight > 0.0) {
        float primary = sin(gameTime * 1.65 
            + inPosition.x * 0.73 + inPosition.z * 0.51 + cloudOffset.x * 0.035);
        float detail = sin(gameTime * 2.47 
            + inPosition.x * 1.31 - inPosition.z * 0.87 + cloudOffset.y * 0.05);
        float motion = (primary * 0.72 + detail * 0.28) * inSwayWeight;
        animatedPosition.x += motion * 0.075;
        animatedPosition.z += motion * 0.032;
    }
    
    // Calculate world position
    vec4 worldPos = modelMatrix * vec4(animatedPosition, 1.0);
    outWorldPos = worldPos.xyz;
    
    // Calculate normal in world space (simplified - assumes identity rotation for now)
    // In full implementation, extract from model matrix or use normal matrix
    outNormal = normalize(mat3(modelMatrix) * vec3(0.0, 0.0, 1.0));
    
    // Pass through color and texture coordinates
    outColor = inColor;
    outTexCoord = inTexCoord;
    outTorchLight = inTorchLight;
    
    // Calculate shadow coordinates for later sampling
    outShadowCoord = shadowMatrix * worldPos;
    
    // View-space position for fog calculation
    vec4 viewPos = viewMatrix * worldPos;
    outFogDistance = length(viewPos.xyz);
    
    // Final clip-space position
    gl_Position = projectionMatrix * viewPos;
}
