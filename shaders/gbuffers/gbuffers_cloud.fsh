// Cloud Fragment Shader - BSL Style Atmosphere
// Generates procedural volumetric-style clouds with time-based animation
#version 330 core

#include "/pipeline_config.glsl"

// Inputs from vertex shader
in vec2 inTexCoord;
in vec3 inWorldPos;
in float inCloudDensity;

// Uniforms
uniform float cloudCoverage;
uniform float gameTime;
uniform float rainStrength;
uniform int renderQuality;

// Output to colortex13 (cloud overlay buffer)
layout(location = 13) out vec4 outClouds;

// Hash function for noise
float hash(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

// 2D Value noise
float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x),
               mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}

// Fractal Brownian Motion for detailed cloud shapes
float fbm(vec2 p, int octaves) {
    float value = 0.0;
    float amplitude = 0.5;
    float frequency = 1.0;
    
    for (int i = 0; i < 6; i++) {
        if (i >= octaves) break;
        value += amplitude * noise(p * frequency);
        amplitude *= 0.5;
        frequency *= 2.0;
    }
    
    return value;
}

void main() {
    // Animate cloud texture coordinates over time
    vec2 animatedUV = inTexCoord;
    animatedUV.x += gameTime * 0.005;  // Slow drift
    
    // Generate cloud density using FBM noise
    int octaves = renderQuality >= QUALITY_HIGH ? 6 : 4;
    float cloudNoise = fbm(animatedUV * 3.0, octaves);
    
    // Apply cloud coverage threshold
    float cloudThreshold = 0.82 - cloudCoverage * 0.45;
    float cloudDensity = smoothstep(cloudThreshold, cloudThreshold + 0.16, cloudNoise);
    
    // Add detail noise for realistic cloud edges
    float detailNoise = noise(animatedUV * 10.0 + gameTime * 0.02);
    cloudDensity *= smoothstep(0.3, 1.0, detailNoise);
    
    // Weather affects cloud density and color
    float weatherMultiplier = 1.0 + rainStrength * 0.5;
    cloudDensity = min(1.0, cloudDensity * weatherMultiplier);
    
    // Discard thin clouds for performance
    if (cloudDensity < 0.05) {
        discard;
    }
    
    // Cloud color based on time of day
    float dayAmount = smoothstep(0.12, 0.85, skyLight);
    
    // Day: bright white with warm tint
    vec3 dayCloudColor = vec3(1.0, 0.98, 0.95);
    // Night: dark blue-gray
    vec3 nightCloudColor = vec3(0.15, 0.18, 0.25);
    // Sunset/sunrise: orange-pink tint
    vec3 sunsetCloudColor = vec3(1.0, 0.75, 0.6);
    
    // Blend based on time
    vec3 cloudColor = mix(nightCloudColor, dayCloudColor, dayAmount);
    
    // Add sunset coloring at dawn/dusk
    float hourOfDay = fract(gameTime / 24.0);
    float isSunset = smoothstep(0.75, 0.79, hourOfDay) * (1.0 - smoothstep(0.83, 0.87, hourOfDay));
    float isSunrise = smoothstep(0.20, 0.24, hourOfDay) * (1.0 - smoothstep(0.28, 0.32, hourOfDay));
    cloudColor = mix(cloudColor, sunsetCloudColor, max(isSunset, isSunrise) * 0.6);
    
    // Weather darkens clouds
    cloudColor *= (1.0 - rainStrength * 0.4);
    
    // Alpha based on density
    float alpha = cloudDensity * 0.8;
    
    outClouds = vec4(cloudColor, alpha);
}
