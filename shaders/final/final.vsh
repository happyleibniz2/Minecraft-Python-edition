// Final Pass Vertex Shader - BSL Style
// Full-screen quad for final output with TAA/FXAA
#version 330 core

#include "/pipeline_config.glsl"

// Full-screen quad vertices
const vec2 quadVertices[4] = vec2[](
    vec2(-1.0, -1.0),
    vec2( 1.0, -1.0),
    vec2(-1.0,  1.0),
    vec2( 1.0,  1.0)
);

layout(location = 0) in int inVertexID;

out vec2 outTexCoord;
out vec4 outScreenPos;

void main() {
    vec2 pos = quadVertices[inVertexID];
    gl_Position = vec4(pos, 0.0, 1.0);
    
    // Convert from [-1,1] to [0,1] UV space
    outTexCoord = pos * 0.5 + 0.5;
    outScreenPos = vec4(pos, 0.0, 1.0);
}
