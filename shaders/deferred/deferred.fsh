// Deferred Lighting Fragment Shader - BSL Style
// Performs lighting calculations using GBuffer data with soft shadows and volumetric light
#version 330 core

#include "/pipeline_config.glsl"

// Inputs from vertex shader
in vec2 inTexCoord;
in vec4 inScreenPos;

// GBuffer textures (from previous gbuffers stage)
uniform sampler2D colortex0;  // Albedo
uniform sampler2D colortex1;  // Specular/Gloss
uniform sampler2D colortex2;  // Normals
uniform sampler2D colortex3;  // Depth
uniform sampler2D shadowMap;  // Shadow map texture

// Uniforms for lighting
uniform vec3 sunDirection;
uniform vec3 sunColor;
uniform vec3 moonColor;
uniform float skyLight;
uniform float gameTime;
uniform float rainStrength;
uniform int shadowEnabled;
uniform int shadowSoftness;
uniform int volumetricLightEnabled;
uniform float volumetricStrength;
uniform vec3 cameraPosition;
uniform vec2 cloudOffset;
uniform float cloudCoverage;
uniform mat4 shadowMatrix;
uniform float viewWidth;
uniform float viewHeight;
uniform mat4 gbufferProjectionInverse;
uniform mat4 inverseViewMatrix;

// Outputs (ping-pong buffers)
layout(location = 0) out vec4 outColor;
layout(location = 1) out vec4 outSpecular;
layout(location = 5) out vec4 outVolumetric;

// Hash function for noise
float hash(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

// 2D Noise function
float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x),
               mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}

// Percentage-Closer Filtering (PCF) for soft shadows - BSL style
float calculateSoftShadow(vec3 shadowCoord) {
    if (shadowEnabled == 0 || shadowCoord.w <= 0.0) {
        return 1.0;
    }
    
    vec3 projected = shadowCoord.xyz / shadowCoord.w;
    
    // Check bounds
    if (projected.x < 0.0 || projected.x > 1.0 ||
        projected.y < 0.0 || projected.y > 1.0 ||
        projected.z < 0.0 || projected.z > 1.0) {
        return 1.0;
    }
    
    // Bias to prevent shadow acne (matching original Light.py value)
    float bias = 0.0018;
    
    // PCF kernel size based on quality setting
    float shadowQuality = float(shadowSoftness);
    float samples = 0.0;
    float lit = 0.0;
    
    if (shadowQuality == 0.0) {
        // No softening - hard shadows
        float centerDepth = texture(shadowMap, projected.xy).r;
        lit = (projected.z - bias <= centerDepth) ? 1.0 : 0.0;
        samples = 1.0;
    } else {
        // PCF filtering with configurable kernel size
        float spread = shadowQuality == 1.0 ? 0.85 : (shadowQuality == 2.0 ? 1.45 : 2.0);
        vec2 texelSize = 1.0 / vec2(textureSize(shadowMap, 0));
        vec2 offset = texelSize * spread;
        
        // 5-tap PCF (center + 4 corners) - matching original shader pattern
        float d0 = texture(shadowMap, projected.xy + vec2(-offset.x, -offset.y)).r;
        float d1 = texture(shadowMap, projected.xy + vec2( offset.x, -offset.y)).r;
        float d2 = texture(shadowMap, projected.xy + vec2(-offset.x,  offset.y)).r;
        float d3 = texture(shadowMap, projected.xy + vec2( offset.x,  offset.y)).r;
        float dc = texture(shadowMap, projected.xy).r;
        
        lit += (projected.z - bias <= d0) ? 1.0 : 0.0;
        lit += (projected.z - bias <= d1) ? 1.0 : 0.0;
        lit += (projected.z - bias <= d2) ? 1.0 : 0.0;
        lit += (projected.z - bias <= d3) ? 1.0 : 0.0;
        lit += (projected.z - bias <= dc) ? 1.0 : 0.0;
        samples = 5.0;
    }
    
    return mix(0.38, 1.0, lit / samples);
}

// Volumetric lighting (godrays) - raymarching through shadow map
vec3 calculateVolumetricLight(vec3 worldPos, float depth, mat4 shadowMatrixInverse) {
    if (volumetricLightEnabled == 0) {
        return vec3(0.0);
    }
    
    // Raymarch FROM the fragment position TOWARDS the sun
    int steps = 16;  // Increased for better quality
    float stepSize = 4.0 / float(steps);  // 4 unit steps in world space
    vec3 lightDir = normalize(sunDirection);
    vec3 volumetricAccumulator = vec3(0.0);
    
    // Add dithering to reduce banding artifacts
    float dither = hash(gl_FragCoord.xy + gameTime * 10.0) * 2.0 - 1.0;
    
    for (int i = 0; i < steps; i++) {
        float t = float(i) * stepSize + dither * stepSize * 0.5;
        vec3 samplePos = worldPos + lightDir * t;
        
        // Transform sample position to light space for shadow lookup
        vec4 lightSpacePos = shadowMatrixInverse * vec4(samplePos, 1.0);
        vec3 projected = lightSpacePos.xyz / lightSpacePos.w;
        
        // Check bounds in light space
        if (projected.x >= 0.0 && projected.x <= 1.0 &&
            projected.y >= 0.0 && projected.y <= 1.0 &&
            projected.z >= 0.0 && projected.z <= 1.0) {
            
            float shadowSample = texture(shadowMap, projected.xy).r;
            float visibility = smoothstep(projected.z - 0.002, projected.z + 0.002, shadowSample);
            
            // Density based on distance from camera (exponential falloff)
            float distToCamera = length(samplePos - cameraPosition);
            float density = exp(-distToCamera * 0.08) * (1.0 - exp(-distToCamera * 0.5));
            
            volumetricAccumulator += sunColor * visibility * density * stepSize * 0.15;
        }
    }
    
    return volumetricAccumulator * volumetricStrength;
}

void main() {
    // Sample GBuffer data
    vec4 albedo = texture(colortex0, inTexCoord);
    vec4 material = texture(colortex1, inTexCoord);
    vec4 normalData = texture(colortex2, inTexCoord);
    vec4 depthData = texture(colortex3, inTexCoord);
    
    // Reconstruct view position from linear depth
    float linearDepth = depthData.r;  // Already normalized [0,1]
    vec2 ndc = gl_FragCoord.xy / vec2(viewWidth, viewHeight) * 2.0 - 1.0;
    vec4 clipPos = vec4(ndc, linearDepth * 2.0 - 1.0, 1.0);
    vec4 viewPos = gbufferProjectionInverse * clipPos;
    viewPos /= viewPos.w;
    vec3 worldPos = (inverseViewMatrix * vec4(viewPos.xyz, 1.0)).xyz;
    
    // Decode normal from [0,1] back to [-1,1]
    vec3 normal = normalData.rgb * 2.0 - 1.0;
    
    // Extract material properties
    float specular = material.r;
    float gloss = material.g;
    
    // Calculate time-based sky color (BSL-style color grading foundation)
    float dayAmount = smoothstep(0.12, 0.85, skyLight);
    vec3 nightSky = vec3(0.34, 0.42, 0.72) * skyLight;
    vec3 daySky = vec3(1.04, 1.00, 0.91) * skyLight;
    vec3 skylight = mix(nightSky, daySky, dayAmount);
    
    // Torch light flicker effect (from original shader)
    float flicker = 0.975 + 0.025 * sin(gameTime * 8.0 + worldPos.x * 1.7 + worldPos.z * 2.3);
    
    // Reconstruct shadow coordinate from world position using shadowMatrix uniform
    vec4 shadowCoord = shadowMatrix * vec4(worldPos, 1.0);
    
    // Calculate soft shadows with PCF
    float shadow = calculateSoftShadow(shadowCoord);
    
    // Apply weather/cloud shadows (from original shader logic)
    float cloudField = noise((worldPos.xz + cloudOffset) * 0.018);
    float cloudThreshold = 0.82 - cloudCoverage * 0.45;
    float cloudDensity = smoothstep(cloudThreshold, cloudThreshold + 0.16, cloudField);
    float cloudShadow = 1.0 - cloudDensity * 0.24 * dayAmount;
    
    // Combine lighting contributions
    float sunShadowStrength = dayAmount * 0.82 * (1.0 - rainStrength * 0.72);
    float finalShadow = mix(1.0, shadow * cloudShadow, sunShadowStrength);
    
    // Calculate final illumination
    vec3 torchColor = vec3(1.18, 0.73, 0.38) * albedo.a * flicker;
    vec3 illumination = max(skylight, torchColor) * finalShadow;
    
    // Apply lighting to albedo
    vec3 litColor = albedo.rgb * illumination;
    
    // Add specular highlights
    vec3 viewDir = normalize(cameraPosition - worldPos);
    vec3 reflectDir = reflect(-sunDirection, normal);
    float specAngle = max(dot(viewDir, reflectDir), 0.0);
    vec3 specularHighlight = pow(specAngle, gloss * 32.0) * sunColor * specular * shadow;
    
    litColor += specularHighlight;
    
    // Calculate volumetric lighting (godrays)
    mat4 shadowMatrixInv = inverse(shadowMatrix);
    vec3 volumetric = calculateVolumetricLight(worldPos, linearDepth, shadowMatrixInv);
    litColor += volumetric;
    
    // Output results
    outColor = vec4(litColor, albedo.a);
    outSpecular = vec4(specularHighlight, 1.0);
    outVolumetric = vec4(volumetric, 1.0);
}
