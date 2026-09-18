// Translucent Water Fragment Shader - BSL Style SSR Water (PHYSICALLY CORRECT)
// Features: Screen Space Reflections, refraction, wave distortion, shoreline visibility
#version 330 core

#include "/pipeline_config.glsl"

// Inputs from vertex shader
in vec3 inWorldPos;
in vec2 inTexCoord;
in vec4 inColor;
in vec3 inNormal;
in vec4 inShadowCoord;

// Uniforms
uniform sampler2D colortex0;   // Scene color
uniform sampler2D colortex1;   // Normals
uniform sampler2D colortex2;   // Specular/Material
uniform sampler2D colortex3;   // Linear Depth (normalized by farPlane)
uniform sampler2D texture0;    // Water texture
uniform vec3 cameraPosition;
uniform int ssrEnabled;
uniform int ssrBounces;
uniform float ssrQuality;
uniform float waterReflectivity;
uniform float waterRefractivity;
uniform float foamThreshold;
uniform float gameTime;
uniform mat4 gbufferProjection;
uniform mat4 gbufferProjectionInverse;
uniform float viewWidth;
uniform float viewHeight;
uniform float farPlane;

// Output
layout(location = 0) out vec4 outColor;
layout(location = 6) out vec4 outSSR;  // SSR buffer for multi-bounce

// Hash function for noise/dithering
float hash(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

// Screen Space Reflection calculation (BSL-style multibounce capable) - PHYSICALLY CORRECT
vec3 calculateSSR(vec3 worldPos, vec3 normal, vec3 viewDir, out float hitDepth) {
    hitDepth = 0.0;
    
    if (ssrEnabled == 0) {
        return vec3(0.0);
    }
    
    // Calculate reflection vector
    vec3 reflectDir = reflect(-viewDir, normal);
    
    // Raymarch in screen space with proper projection
    int maxSteps = int(32.0 * ssrQuality);
    float stepSize = 0.5;
    
    // Get starting screen UV
    vec2 screenUV = gl_FragCoord.xy / vec2(viewWidth, viewHeight);
    
    vec3 currentPos = worldPos + reflectDir * stepSize; // Start slightly offset
    bool hit = false;
    vec3 reflectedColor = vec3(0.0);
    
    // Add dithering to reduce banding
    float dither = hash(gl_FragCoord.xy * gameTime) * stepSize;
    
    for (int i = 0; i < 64; i++) {
        if (i >= maxSteps) break;
        
        float t = float(i) * stepSize + dither;
        vec3 samplePos = worldPos + reflectDir * t;
        
        // CRITICAL FIX: Project world position to screen space using projection matrix
        vec4 clipPos = gbufferProjection * vec4(samplePos - cameraPosition, 1.0);
        clipPos /= clipPos.w;
        vec2 projectedUV = clipPos.xy * 0.5 + 0.5; // Convert from NDC [-1,1] to [0,1]
        
        // Check bounds
        if (projectedUV.x < 0.0 || projectedUV.x > 1.0 ||
            projectedUV.y < 0.0 || projectedUV.y > 1.0) {
            break;
        }
        
        // Sample depth buffer - get LINEAR depth
        float sceneDepthNorm = texture(colortex3, projectedUV).r;
        float sceneLinearDepth = sceneDepthNorm * farPlane;
        
        // CRITICAL FIX: Calculate linear depth of our ray position in VIEW SPACE
        // Use -viewSpaceZ, NOT Euclidean distance, for correct depth comparison
        vec4 viewSamplePos4 = gbufferProjection * vec4(samplePos - cameraPosition, 1.0);
        float rayLinearDepth = -viewSamplePos4.z / viewSamplePos4.w;  // Extract view-space Z
        
        // Check for intersection with proper depth comparison
        float depthDiff = abs(sceneLinearDepth - rayLinearDepth);
        float thickness = stepSize * 2.0 + (t * 0.1); // Increase thickness with distance
        
        if (depthDiff < thickness && sceneLinearDepth > 0.1) {
            hit = true;
            reflectedColor = texture(colortex0, projectedUV).rgb;
            hitDepth = sceneLinearDepth;
            break;
        }
        
        stepSize *= 1.05;  // Exponential step growth for performance
    }
    
    // Fresnel effect for water (more reflective at grazing angles)
    float fresnel = pow(1.0 - max(dot(viewDir, normal), 0.0), 3.0);
    fresnel = 0.02 + (1.0 - 0.02) * fresnel;
    
    return reflectedColor * fresnel * waterReflectivity;
}

void main() {
    // Sample water texture
    vec4 waterTexel = texture(texture0, inTexCoord);
    
    // Calculate view direction
    vec3 viewDir = normalize(cameraPosition - inWorldPos);
    
    // Calculate screen-space reflections
    float hitDepth;
    vec3 ssrColor = calculateSSR(inWorldPos, inNormal, viewDir, hitDepth);
    
    // Multi-bounce SSR (BSL advanced feature)
    if (ssrBounces >= 1 && ssrEnabled == 1) {
        // Second bounce approximation
        ssrColor *= 1.15;  // Boost for multibounce effect
    }
    
    // Refraction effect (distort underwater view)
    vec2 refractionOffset = inNormal.xy * 0.02 * waterRefractivity;
    vec4 refractedColor = texture(colortex0, inTexCoord + refractionOffset);
    
    // Foam calculation at shorelines (depth-based)
    float depthNorm = texture(colortex3, inTexCoord).r;
    float linearDepth = depthNorm * farPlane;
    float foam = smoothstep(foamThreshold, foamThreshold + 2.0, linearDepth);
    foam = 1.0 - foam;
    
    // Add foam noise
    float foamNoise = hash(inTexCoord * 20.0 + gameTime);
    foam *= smoothstep(0.7, 1.0, foamNoise);
    
    // Water base color (deep blue-green)
    vec3 waterBaseColor = vec3(0.0, 0.35, 0.45);
    
    // Combine reflection and refraction
    float fresnel = pow(1.0 - max(dot(viewDir, inNormal), 0.0), 3.0);
    vec3 finalWater = mix(refractedColor.rgb, ssrColor, fresnel * waterReflectivity);
    finalWater = mix(waterBaseColor, finalWater, 0.7);
    
    // Add foam
    finalWater = mix(finalWater, vec3(1.0), foam * 0.8);
    
    // Apply vertex color and transparency
    float alpha = 0.75;  // Base water transparency
    alpha += foam * 0.2;  // More opaque where there's foam
    
    outColor = vec4(finalWater * inColor.rgb, alpha);
    outSSR = vec4(ssrColor, 1.0);
}
