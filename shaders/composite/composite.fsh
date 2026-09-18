// Composite Fragment Shader - BSL Style Post-Processing
// Applies bloom, color grading, and atmospheric effects
#version 330 core

#include "/pipeline_config.glsl"

// Inputs from vertex shader (full-screen quad)
in vec2 inTexCoord;

// Input textures from deferred stage
uniform sampler2D colortex0;   // Lit color
uniform sampler2D colortex1;   // Specular
uniform sampler2D colortex5;   // Volumetric light
uniform sampler2D colortex7;   // Bloom highlights
uniform sampler2D colortex13;  // Clouds overlay

// Uniforms for post-processing
uniform float exposure;
uniform float brightness;
uniform float saturation;
uniform float vibrance;
uniform int bloomEnabled;
uniform float bloomStrength;
uniform int dofEnabled;
uniform float dofFocus;
uniform float dofAperture;
uniform int motionBlurEnabled;
uniform float motionBlurStrength;
uniform float gameTime;
uniform float rainStrength;
uniform int biomeType;

// Output to final buffer
layout(location = 0) out vec4 outColor;

// Time-based color grading LUT approximation (BSL style)
vec3 applyTimeBasedColorGrading(vec3 color, float time) {
    // Normalize time to 0-1 over 24 hours
    float normalizedTime = fract(time / 24.0);
    
    // Dawn (5-7 AM): cool pastels
    vec3 dawnTint = vec3(1.0, 0.85, 0.9);
    float dawnWeight = smoothstep(5.0/24.0, 6.0/24.0, normalizedTime) * 
                       (1.0 - smoothstep(7.0/24.0, 8.0/24.0, normalizedTime));
    
    // Noon (10 AM - 2 PM): warm saturation boost
    vec3 noonTint = vec3(1.05, 1.02, 0.95);
    float noonWeight = smoothstep(10.0/24.0, 11.0/24.0, normalizedTime) * 
                       (1.0 - smoothstep(14.0/24.0, 15.0/24.0, normalizedTime));
    
    // Dusk/Sunset (6-8 PM): orange tones
    vec3 duskTint = vec3(1.0, 0.75, 0.5);
    float duskWeight = smoothstep(18.0/24.0, 19.0/24.0, normalizedTime) * 
                       (1.0 - smoothstep(20.0/24.0, 21.0/24.0, normalizedTime));
    
    // Night: cool blue tint
    vec3 nightTint = vec3(0.7, 0.8, 1.0);
    float nightWeight = smoothstep(21.0/24.0, 22.0/24.0, normalizedTime) + 
                        (1.0 - smoothstep(4.0/24.0, 5.0/24.0, normalizedTime));
    
    // Apply tints with weights
    vec3 gradedColor = color;
    gradedColor = mix(gradedColor, gradedColor * dawnTint, dawnWeight * 0.3);
    gradedColor = mix(gradedColor, gradedColor * noonTint, noonWeight * 0.2);
    gradedColor = mix(gradedColor, gradedColor * duskTint, duskWeight * 0.4);
    gradedColor = mix(gradedColor, gradedColor * nightTint, nightWeight * 0.25);
    
    return gradedColor;
}

// Saturation and vibrance adjustment
vec3 adjustSaturationVibrance(vec3 color, float sat, float vib) {
    float luminance = dot(color, vec3(0.2126, 0.7152, 0.0722));
    
    // Standard saturation
    vec3 saturated = mix(vec3(luminance), color, sat);
    
    // Vibrance (protects already-saturated colors)
    float maxChannel = max(color.r, max(color.g, color.b));
    float vibranceAmount = (1.0 - maxChannel) * vib;
    saturated += vibranceAmount;
    
    return saturated;
}

// Simple Gaussian blur for bloom
vec3 gaussianBlur(sampler2D tex, vec2 uv, vec2 texelSize, float radius) {
    if (radius < 1.0) {
        return texture(tex, uv).rgb;
    }
    
    vec3 result = vec3(0.0);
    float totalWeight = 0.0;
    
    // 5x5 kernel for performance
    for (float x = -2.0; x <= 2.0; x++) {
        for (float y = -2.0; y <= 2.0; y++) {
            vec2 offset = vec2(x, y) * texelSize * radius;
            float weight = exp(-(x*x + y*y) / 8.0);
            result += texture(tex, uv + offset).rgb * weight;
            totalWeight += weight;
        }
    }
    
    return result / totalWeight;
}

// Depth of field (simplified bokeh approximation)
vec3 applyDepthOfField(vec3 color, float depth) {
    if (dofEnabled == 0) {
        return color;
    }
    
    float focusDistance = dofFocus;
    float aperture = dofAperture;
    
    // Calculate blur amount based on distance from focal plane
    float blurAmount = abs(depth - focusDistance) * aperture * 0.01;
    blurAmount = clamp(blurAmount, 0.0, 1.0);
    
    if (blurAmount < 0.01) {
        return color;
    }
    
    // Simple blur approximation
    vec2 texelSize = 1.0 / screenSize;
    vec3 blurred = gaussianBlur(colortex0, inTexCoord, texelSize, blurAmount * 3.0);
    
    return mix(color, blurred, blurAmount);
}

void main() {
    // Sample lit color from deferred pass
    vec3 color = texture(colortex0, inTexCoord).rgb;
    
    // Add volumetric lighting (godrays)
    if (volumetricLightEnabled == 1) {
        vec3 volumetric = texture(colortex5, inTexCoord).rgb;
        color += volumetric * volumetricStrength;
    }
    
    // Apply bloom effect
    if (bloomEnabled == 1) {
        vec3 bloomHighlights = texture(colortex7, inTexCoord).rgb;
        vec2 texelSize = 1.0 / screenSize;
        
        // Multi-pass bloom blur
        vec3 bloomBlurred = gaussianBlur(colortex7, inTexCoord, texelSize, 2.0);
        bloomBlurred = gaussianBlur(sampler2D(colortex7), inTexCoord, texelSize, 4.0);
        
        color += bloomBlurred * bloomStrength * 0.5;
    }
    
    // Apply clouds overlay
    vec4 clouds = texture(colortex13, inTexCoord);
    if (clouds.a > 0.01) {
        color = mix(color, clouds.rgb, clouds.a * 0.6);
    }
    
    // Apply weather effects
    if (rainStrength > 0.01) {
        // Desaturate and darken during rain
        color *= (1.0 - rainStrength * 0.3);
        float grayScale = dot(color, vec3(0.299, 0.587, 0.114));
        color = mix(color, vec3(grayScale), rainStrength * 0.4);
    }
    
    // Apply biome-specific fog/atmosphere
    float fogAmount = 0.0;
    vec3 fogColor = vec3(0.5, 0.7, 1.0);  // Default temperate
    
    if (biomeType == 1) {  // Desert
        fogColor = vec3(1.0, 0.85, 0.6);
    } else if (biomeType == 2) {  // Snow/Taiga
        fogColor = vec3(0.8, 0.85, 0.95);
    } else if (biomeType == 3) {  // Swamp
        fogColor = vec3(0.6, 0.7, 0.5);
    }
    
    // Apply exposure and brightness
    color = color * exposure + brightness;
    
    // Apply time-based color grading (BSL signature feature)
    color = applyTimeBasedColorGrading(color, gameTime);
    
    // Apply saturation and vibrance
    color = adjustSaturationVibrance(color, saturation, vibrance);
    
    // Apply depth of field
    float depth = texture(colortex3, inTexCoord).r * 256.0;
    color = applyDepthOfField(color, depth);
    
    // Tone mapping (Reinhard operator for cinematic look)
    color = color / (color + vec3(1.0));
    
    // Gamma correction
    color = pow(color, vec3(1.0 / 2.2));
    
    // Final contrast boost (BSL-style)
    color = (color - 0.5) * 1.05 + 0.5;
    
    // Clamp to valid range
    color = clamp(color, 0.0, 1.0);
    
    outColor = vec4(color, 1.0);
}
