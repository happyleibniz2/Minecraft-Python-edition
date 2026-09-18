// Final Pass Fragment Shader - BSL Style
// Applies TAA (Temporal Anti-Aliasing) and FXAA as final post-processing
#version 330 core

#include "/pipeline_config.glsl"

// Inputs from vertex shader
in vec2 inTexCoord;
in vec4 inScreenPos;

// Input textures
uniform sampler2D colortex0;       // Composite output
uniform sampler2D colortex10;      // Previous frame (for TAA)
uniform sampler2D colortex3;       // Depth buffer
uniform sampler2D colortex11;      // Motion vectors

// Uniforms
uniform int taaEnabled;
uniform int fxaaEnabled;
uniform int frameCounter;
uniform float gameTime;
uniform vec2 texelSize;
uniform mat4 inverseProjectionMatrix;
uniform mat4 inverseViewMatrix;
uniform mat4 previousViewProjectionMatrix;

// Output to screen
layout(location = 0) out vec4 outColor;

// FXAA Edge Detection and Smoothing (NVIDIA FXAA3.11 inspired, simplified)
vec3 applyFXAA(sampler2D tex, vec2 uv) {
    if (fxaaEnabled == 0) {
        return texture(tex, uv).rgb;
    }
    
    vec3 rgbNW = texture(tex, uv + vec2(-1.0, -1.0) * texelSize).rgb;
    vec3 rgbNE = texture(tex, uv + vec2( 1.0, -1.0) * texelSize).rgb;
    vec3 rgbSW = texture(tex, uv + vec2(-1.0,  1.0) * texelSize).rgb;
    vec3 rgbSE = texture(tex, uv + vec2( 1.0,  1.0) * texelSize).rgb;
    vec3 rgbM  = texture(tex, uv).rgb;
    
    // Calculate luminance
    float lumaNW = dot(rgbNW, vec3(0.299, 0.587, 0.114));
    float lumaNE = dot(rgbNE, vec3(0.299, 0.587, 0.114));
    float lumaSW = dot(rgbSW, vec3(0.299, 0.587, 0.114));
    float lumaSE = dot(rgbSE, vec3(0.299, 0.587, 0.114));
    float lumaM  = dot(rgbM,  vec3(0.299, 0.587, 0.114));
    
    // Find min/max luminance for edge detection
    float lumaMin = min(lumaM, min(min(lumaNW, lumaNE), min(lumaSW, lumaSE)));
    float lumaMax = max(lumaM, max(max(lumaNW, lumaNE), max(lumaSW, lumaSE)));
    
    float lumaRange = lumaMax - lumaMin;
    
    // Skip if not enough contrast (not an edge)
    if (lumaRange < 0.01) {
        return rgbM;
    }
    
    // Calculate edge directions
    float edgeHorizontal = abs((lumaNW + lumaNE) - (lumaSW + lumaSE)) * 0.25;
    float edgeVertical   = abs((lumaNW + lumaSW) - (lumaNE + lumaSE)) * 0.25;
    
    // Determine dominant edge direction
    bool isHorizontal = edgeHorizontal > edgeVertical;
    
    // Sample along the edge for blending
    vec2 sampleOffset = isHorizontal ? vec2(0.0, 1.0) : vec2(1.0, 0.0);
    vec3 blendSample = texture(tex, uv + sampleOffset * texelSize).rgb;
    
    // Blend original with edge-smoothed sample
    float blendWeight = 0.5;
    return mix(rgbM, blendSample, blendWeight);
}

// Temporal Anti-Aliasing (TAA) - reproject previous frame
vec3 applyTAA(vec3 currentColor, vec2 uv, float depth) {
    if (taaEnabled == 0 || frameCounter == 0) {
        return currentColor;
    }
    
    // Reproject current pixel to previous frame's UV space
    // This requires motion vectors or full matrix reconstruction
    
    // Simplified approach: use motion vectors from colortex11
    vec2 motionVector = texture(colortex11, uv).rg;
    vec2 previousUV = uv - motionVector;
    
    // Clamp to valid UV range
    if (previousUV.x < 0.0 || previousUV.x > 1.0 ||
        previousUV.y < 0.0 || previousUV.y > 1.0) {
        return currentColor;
    }
    
    // Sample previous frame
    vec3 previousColor = texture(colortex10, previousUV).rgb;
    
    // Neighborhood clamping to prevent ghosting
    vec3 minColor = min(currentColor, previousColor);
    vec3 maxColor = max(currentColor, previousColor);
    
    // Blend current and previous frames
    float taaBlend = 0.7;  // Higher weight on current frame to reduce ghosting
    vec3 blended = mix(previousColor, currentColor, taaBlend);
    
    // Clamp to neighborhood to prevent artifacts
    blended = clamp(blended, minColor, maxColor);
    
    return blended;
}

// Film grain effect (optional, for cinematic look)
float filmGrain(vec2 uv, float time) {
    float grain = hash(uv * 100.0 + time * 60.0);
    grain = fract(sin(dot(uv, vec2(12.9898, 78.233))) * 43758.5453);
    return grain * 0.05;  // Subtle grain amount
}

// Vignette effect
float vignette(vec2 uv) {
    vec2 center = vec2(0.5);
    float dist = distance(uv, center);
    return smoothstep(0.8, 0.2, dist);
}

void main() {
    // Sample composite output
    vec3 color = texture(colortex0, inTexCoord).rgb;
    
    // Get depth for TAA reprojection
    float depth = texture(colortex3, inTexCoord).r;
    
    // Apply TAA first (temporal accumulation)
    color = applyTAA(color, inTexCoord, depth);
    
    // Apply FXAA for additional spatial smoothing
    color = applyFXAA(colortex0, inTexCoord);
    
    // Add subtle film grain for cinematic feel
    float grain = filmGrain(inTexCoord, gameTime);
    color += grain;
    
    // Apply vignette (darken edges)
    float vignetteAmount = vignette(inTexCoord);
    color *= mix(0.85, 1.0, vignetteAmount);
    
    // Final gamma correction and tone mapping
    color = pow(color, vec3(1.0 / 2.2));
    color = clamp(color, 0.0, 1.0);
    
    outColor = vec4(color, 1.0);
}
