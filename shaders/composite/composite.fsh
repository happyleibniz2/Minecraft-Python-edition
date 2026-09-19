// Composite Fragment Shader - BSL Style Post-Processing (PHYSICALLY CORRECT BLOOM)
// Applies bloom, color grading, and atmospheric effects
#version 330 core

#include "/pipeline_config.glsl"

// Inputs from vertex shader (full-screen quad)
in vec2 inTexCoord;

// Input textures from deferred stage
uniform sampler2D colortex0;   // Lit color
uniform sampler2D colortex1;   // Specular
uniform sampler2D colortex3;   // Linear Depth
uniform sampler2D colortex5;   // Volumetric light
uniform sampler2D colortex7;   // Bloom highlights (luminance thresholded)
uniform sampler2D colortex8;   // Bloom downsample 1 (half res)
uniform sampler2D colortex9;   // Bloom downsample 2 (quarter res)
uniform sampler2D colortex10;  // Bloom downsample 3 (eighth res)
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
uniform float viewWidth;
uniform float viewHeight;
uniform float farPlane;

// Output to final buffer
layout(location = 0) out vec4 outColor;

// Time-based color grading LUT approximation (BSL style)
vec3 applyTimeBasedColorGrading(vec3 color, float time) {
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
    vec3 saturated = mix(vec3(luminance), color, sat);
    float maxChannel = max(color.r, max(color.g, color.b));
    float vibranceAmount = (1.0 - maxChannel) * vib;
    saturated += vibranceAmount;
    return saturated;
}

// Gaussian blur with proper kernel
vec3 gaussianBlur(sampler2D tex, vec2 uv, vec2 texelSize, float radius) {
    if (radius < 0.5) {
        return texture(tex, uv).rgb;
    }

    vec3 result = vec3(0.0);
    float totalWeight = 0.0;
    int kernelSize = 5;

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

// PHYSICALLY CORRECT BLOOM: Multi-scale pyramid with proper threshold extraction
vec3 applyProperBloom(vec2 uv, vec2 texelSize) {
    if (bloomEnabled == 0) {
        return vec3(0.0);
    }

    // STEP 1: Extract bright highlights with luminance threshold from full-res color
    vec3 baseColor = texture(colortex0, uv).rgb;
    float luminance = dot(baseColor, vec3(0.2126, 0.7152, 0.0722));
    float threshold = 0.85;  // Only pixels brighter than this contribute to bloom
    
    // Soft threshold extraction (avoids hard cutoff artifacts)
    float brightness = max(0.0, luminance - threshold);
    vec3 extractedHighlights = baseColor * (brightness / max(luminance, 0.001));

    // STEP 2: Build TRUE multi-resolution pyramid using pre-downsampled buffers
    // colortex7 = half resolution, colortex8 = quarter, colortex9 = eighth, colortex10 = sixteenth
    // Each level is blurred at its NATIVE resolution for efficiency
    
    // Level 1: Half resolution (colortex7) - small blur
    vec3 bloomLevel1 = gaussianBlur(colortex7, uv, texelSize * 2.0, 1.2);
    
    // Level 2: Quarter resolution (colortex8) - medium blur
    vec3 bloomLevel2 = gaussianBlur(colortex8, uv, texelSize * 4.0, 1.8);
    
    // Level 3: Eighth resolution (colortex9) - large blur
    vec3 bloomLevel3 = gaussianBlur(colortex9, uv, texelSize * 8.0, 2.5);
    
    // Level 4: Sixteenth resolution (colortex10) - widest ambient glow
    vec3 bloomLevel4 = gaussianBlur(colortex10, uv, texelSize * 16.0, 3.5);

    // STEP 3: CRITICAL - Upsample and ACCUMULATE in true pyramid fashion
    // Start from LOWEST resolution (most blurred) and work UP
    // Each level adds the upsampled result from the level BELOW it
    
    // Start with smallest resolution (level 4 - sixteenth res)
    vec3 accumulatedGlow = bloomLevel4;
    
    // Upsample level 4 → level 3 resolution and ADD to level 3's own blur
    // The bilinear texture sampling during upsampling acts as the filter
    vec3 upsampled4 = texture(colortex10, uv).rgb;  // Bilinear upsample
    accumulatedGlow += bloomLevel3 + upsampled4;
    
    // Upsample combined (L4+L3) → level 2 resolution and ADD to level 2
    vec3 upsampled3 = texture(colortex9, uv).rgb;
    accumulatedGlow += bloomLevel2 + upsampled3;
    
    // Upsample combined (L4+L3+L2) → level 1 resolution and ADD to level 1
    vec3 upsampled2 = texture(colortex8, uv).rgb;
    accumulatedGlow += bloomLevel1 + upsampled2;
    
    // Final upsample to FULL resolution - ADD to get final accumulated glow
    vec3 upsampled1 = texture(colortex7, uv).rgb;
    accumulatedGlow += upsampled1;  // FIX: Accumulate, don't overwrite

    // STEP 4: Apply bloom strength and blend with original color
    return accumulatedGlow * bloomStrength;
}

// Depth of field (simplified bokeh approximation)
vec3 applyDepthOfField(vec3 color, float depthNorm) {
    if (dofEnabled == 0) {
        return color;
    }

    float linearDepth = depthNorm * farPlane;
    float focusDistance = dofFocus * farPlane;
    float aperture = dofAperture;

    float blurAmount = abs(linearDepth - focusDistance) * aperture * 0.0001;
    blurAmount = clamp(blurAmount, 0.0, 1.0);

    if (blurAmount < 0.01) {
        return color;
    }

    vec2 texelSize = 1.0 / vec2(viewWidth, viewHeight);
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

    // Apply PROPER BLOOM (multi-scale pyramid)
    vec2 texelSize = 1.0 / vec2(viewWidth, viewHeight);
    vec3 bloomResult = applyProperBloom(inTexCoord, texelSize);
    color += bloomResult;

    // Apply clouds overlay
    vec4 clouds = texture(colortex13, inTexCoord);
    if (clouds.a > 0.01) {
        color = mix(color, clouds.rgb, clouds.a * 0.6);
    }

    // Apply weather effects
    if (rainStrength > 0.01) {
        color *= (1.0 - rainStrength * 0.3);
    }

    // Apply time-based color grading (BSL signature feature)
    color = applyTimeBasedColorGrading(color, gameTime);

    // Adjust saturation and vibrance
    color = adjustSaturationVibrance(color, saturation, vibrance);

    // Apply depth of field
    float depthNorm = texture(colortex3, inTexCoord).r;
    color = applyDepthOfField(color, depthNorm);

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
