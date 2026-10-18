// cpp/cloud_math.cpp
// CPU-side (MSVC) verification of the volumetric-cloud GLSL 1.20 math in
// game/world/Clouds.py.  All arithmetic in `float` to mirror GLSL float
// semantics.  Build & run with cpp\build_and_run.cmd.
#include <cmath>
#include <cstdio>
#include <algorithm>

static const double PI_D = 3.14159265358979323846;

static int failures = 0;
static void check(bool ok, const char* what) {
    std::printf("%s  %s\n", ok ? "PASS" : "FAIL", what);
    if (!ok) ++failures;
}

// GLSL built-in mirrors ---------------------------------------------------
static float fractf(float x) { return x - std::floor(x); }
static float clampf(float x, float lo, float hi) {
    return std::min(hi, std::max(lo, x));
}
static float mixf(float a, float b, float t) { return a + (b - a) * t; }
static float ss(float e0, float e1, float x) {
    float t = clampf((x - e0) / (e1 - e0), 0.0f, 1.0f);
    return t * t * (3.0f - 2.0f * t);
}
struct v3 { float x, y, z; };

// Clouds.py: hash31 (fragment shader) ---------------------------------------
static float hash31(v3 p) {
    p.x = fractf(p.x * 0.1031f);
    p.y = fractf(p.y * 0.1030f);
    p.z = fractf(p.z * 0.0973f);
    float d = p.x * (p.y + 33.33f) + p.y * (p.z + 33.33f)
               + p.z * (p.x + 33.33f);  // dot(p, p.yzx + 33.33)
    p.x += d; p.y += d; p.z += d;
    return fractf((p.x + p.y) * p.z);
}

// Clouds.py: valueNoise3 ----------------------------------------------------
static float valueNoise3(v3 p) {
    v3 c = { std::floor(p.x), std::floor(p.y), std::floor(p.z) };
    v3 l = { p.x - c.x, p.y - c.y, p.z - c.z };
    l.x = l.x*l.x*l.x*(l.x*(l.x*6.0f - 15.0f) + 10.0f);
    l.y = l.y*l.y*l.y*(l.y*(l.y*6.0f - 15.0f) + 10.0f);
    l.z = l.z*l.z*l.z*(l.z*(l.z*6.0f - 15.0f) + 10.0f);
    float n000 = hash31({c.x, c.y, c.z});
    float n100 = hash31({c.x + 1, c.y, c.z});
    float n010 = hash31({c.x, c.y + 1, c.z});
    float n110 = hash31({c.x + 1, c.y + 1, c.z});
    float n001 = hash31({c.x, c.y, c.z + 1});
    float n101 = hash31({c.x + 1, c.y, c.z + 1});
    float n011 = hash31({c.x, c.y + 1, c.z + 1});
    float n111 = hash31({c.x + 1, c.y + 1, c.z + 1});
    float lo = mixf(mixf(n000, n100, l.x), mixf(n010, n110, l.x), l.y);
    float hi = mixf(mixf(n001, n101, l.x), mixf(n011, n111, l.x), l.y);
    return mixf(lo, hi, l.z);
}

// Clouds.py: fbm (5 octaves) -------------------------------------------------
static float fbm(v3 p) {
    float value = 0.0f, amp = 0.5f, freq = 1.0f;
    for (int i = 0; i < 5; ++i) {
        value += amp * valueNoise3({p.x * freq, p.y * freq, p.z * freq});
        amp *= 0.5f;
        freq *= 2.02f;
    }
    return value;
}

// Clouds.py: worleyNoise -----------------------------------------------------
static float worleyNoise(v3 p) {
    v3 c = { std::floor(p.x), std::floor(p.y), std::floor(p.z) };
    v3 l = { p.x - c.x, p.y - c.y, p.z - c.z };
    float minDist = 1.0f;
    for (int x = -1; x <= 1; ++x)
        for (int y = -1; y <= 1; ++y)
            for (int z = -1; z <= 1; ++z) {
                v3 n = { (float)x, (float)y, (float)z };
                v3 q = { c.x + n.x, c.y + n.y, c.z + n.z };
                v3 pt = {
                    hash31({q.x, q.y + 100.0f, q.z + 200.0f}),
                    hash31({q.x + 100.0f, q.y, q.z + 300.0f}),
                    hash31({q.x + 200.0f, q.y + 300.0f, q.z})
                };
                float dx = l.x - n.x - pt.x;
                float dy = l.y - n.y - pt.y;
                float dz = l.z - n.z - pt.z;
                minDist = std::min(minDist,
                                   std::sqrt(dx * dx + dy * dy + dz * dz));
            }
    return minDist;
}

// Clouds.py: cloudDensity (MEDIUM-tier path, uDetail=1) ---------------------
struct DensityParams {
    float cloudBase = 88.0f, cloudTop = 112.0f;
    float windX = 100.0f, windZ = 40.0f;
    float coverage = 0.56f, weather = 0.0f;
    float gameTime = 0.0f;
    float uDetail = 1.0f;
};

static float cloudDensity(const DensityParams& u, v3 world) {
    float height = clampf((world.y - u.cloudBase) / (u.cloudTop - u.cloudBase),
                         0.0f, 1.0f);
    float bottom = ss(0.0f, 0.18f, height);
    float top = 1.0f - ss(0.55f, 1.0f, height);
    float anvil = mixf(0.7f, 1.3f, ss(0.1f, 0.75f, height));
    // NOTE: the shader currently writes smoothstep(1.0, 0.65, height) -
    // reversed edges.  Mirror what typical drivers compute for it (the
    // clamp formula) so the port matches the observed GPU behaviour.
    float heightGradient = ss(0.0f, 0.25f, height) * ss(1.0f, 0.65f, height);

    v3 sp = { (world.x + u.windX) * 0.006f, height * 1.6f,
              (world.z + u.windZ) * 0.006f };
    float baseShape = fbm(sp) * anvil;
    float cellStructure = worleyNoise({sp.x * 2.0f + u.gameTime * 0.002f,
                                       sp.y * 2.0f, sp.z * 2.0f});
    float shape = mixf(baseShape, cellStructure, 0.3f);

    float threshold = 0.65f - u.coverage * 0.35f - u.weather * 0.1f;
    float density = (shape - threshold) * 3.4f;
    density = clampf(density, 0.0f, 1.0f);
    density = std::pow(density, 1.2f);

    float detailNoise = valueNoise3({sp.x * 5.0f, sp.y * 5.0f + u.gameTime * 0.003f,
                                     sp.z * 5.0f});
    density *= 0.85f + 0.15f * detailNoise;

    if (u.uDetail > 0.5f) {
        float erode = worleyNoise({sp.x * 4.0f + u.windX * 0.05f,
                                   sp.y * 4.0f + u.gameTime * 0.004f,
                                   sp.z * 4.0f + u.windZ * 0.05f});
        density -= erode * 0.3f * (1.0f - density);
    }
    return clampf(density * bottom * top * heightGradient, 0.0f, 1.0f);
}

// Clouds.py: hgPhase ---------------------------------------------------------
static float hgPhase(float cosTheta, float g) {
    float denom = std::max(
        std::pow(1.0f + g * g - 2.0f * g * cosTheta, 1.5f), 0.0001f);
    return (1.0f - g * g) / (12.566f * denom);
}

int main() {
    std::printf("== cloud math verification (float, mirrors GLSL 1.20) ==\n");

    // 1. hash31 range + statistics ------------------------------------------
    {
        float mn = 1.0f, mx = 0.0f, sum = 0.0f, sum2 = 0.0f;
        const int N = 100000;
        for (int i = 0; i < N; ++i) {
            float h = hash31({ (float)(i * 7), (float)(i * 13),
                               (float)(i % 97) });
            mn = std::min(mn, h); mx = std::max(mx, h);
            sum += h; sum2 += h * h;
        }
        float mean = sum / N;
        float var = sum2 / N - mean * mean;
        check(mn >= 0.0f && mx < 1.0f, "hash31 stays in [0,1)");
        check(std::abs(mean - 0.5f) < 0.02f, "hash31 mean ~ 0.5");
        check(var > 0.05f, "hash31 has real variance (not degenerate)");
        std::printf("      hash31 mean=%.4f var=%.4f min=%.4f max=%.4f\n",
                    mean, var, mn, mx);
    }

    // 2. valueNoise3 / fbm ranges -------------------------------------------
    {
        float mn = 1e9f, mx = -1e9f;
        bool in_range = true;
        for (int i = 0; i < 20000; ++i) {
            v3 p = { i * 0.37f, i * 0.61f, i * 0.23f };
            float n = valueNoise3(p);
            if (!(n >= 0.0f && n <= 1.0f)) in_range = false;
            mn = std::min(mn, n); mx = std::max(mx, n);
        }
        check(in_range, "valueNoise3 in [0,1] over 20k samples");
        float fmn = 1e9f, fmx = -1e9f;
        for (int i = 0; i < 20000; ++i) {
            float f = fbm({ i * 0.11f, i * 0.07f, i * 0.05f });
            fmn = std::min(fmn, f); fmx = std::max(fmx, f);
        }
        check(fmn >= 0.0f && fmx <= 1.0f, "fbm in [0,1] (5 octaves, max ~0.97)");
        std::printf("      valueNoise3 [%.4f, %.4f]  fbm [%.4f, %.4f]\n",
                    mn, mx, fmn, fmx);
    }

    // 3. cloudDensity range over the whole slab ------------------------------
    {
        DensityParams u;
        float mn = 1e9f, mx = -1e9f;
        long zero = 0, total = 0;
        bool in_range = true;
        for (int yi = 0; yi <= 40 && in_range; ++yi)
            for (int xi = 0; xi < 200 && in_range; ++xi)
                for (int zi = 0; zi < 200; ++zi) {
                    v3 w = { xi * 3.0f - 300.0f, 88.0f + yi * 0.6f,
                             zi * 3.0f - 300.0f };
                    float d = cloudDensity(u, w);
                    if (!(d >= 0.0f && d <= 1.0f)) { in_range = false; break; }
                    mn = std::min(mn, d); mx = std::max(mx, d);
                    ++total;
                    if (d <= 0.003f) ++zero;
                }
        check(in_range, "cloudDensity in [0,1] over a 1.6M-cell slab sweep");
        std::printf("      density range [%.4f, %.4f], empty cells: %ld/%ld\n",
                    mn, mx, zero, total);
        check(mx > 0.2f, "density actually reaches cloud values");
        float empty = (float)zero / total;
        check(empty > 0.2f && empty < 0.95f,
              "density field has clouds AND gaps (adaptive march matters)");
    }

    // 4. Henyey-Greenstein phase vs double reference -------------------------
    {
        bool all_ok = true;
        for (float g : {0.55f, -0.25f}) {
            for (int i = 0; i <= 100; ++i) {
                float ct = -1.0f + 2.0f * i / 100.0f;
                float got = hgPhase(ct, g);
                double ref = (1.0 - (double)g * g)
                    / (4.0 * PI_D
                       * std::pow(1.0 + (double)g * g - 2.0 * g * ct, 1.5));
                if (!(got >= 0.0f) || std::abs(got - ref) > 1e-4) all_ok = false;
            }
        }
        check(all_ok, "hgPhase matches (1-g^2)/(4*pi*(1+g^2-2g cos)^1.5)");
        check(hgPhase(1.0f, 0.55f) > hgPhase(0.0f, 0.55f)
              && hgPhase(0.0f, 0.55f) > hgPhase(-1.0f, 0.55f),
              "hgPhase forward-scattering peak for g>0");
    }

    // 5. full march invariants (MEDIUM tier) ----------------------------------
    {
        DensityParams u;
        v3 cam = { 0.0f, 80.0f, 0.0f };
        float len = std::sqrt(0.866f * 0.866f + 0.5f * 0.5f);
        v3 dir = { 0.0f, 0.866f / len, -0.5f / len };  // 60 deg up
        float first = (u.cloudBase - cam.y) / dir.y;
        float second = (u.cloudTop - cam.y) / dir.y;
        float nearD = std::max(0.0f, std::min(first, second));
        float farD = std::min(360.0f, std::max(first, second));
        float baseStep = (farD - nearD) / 16.0f;
        float t = nearD;
        float trans = 1.0f, prev_trans = 1.0f;
        float acc[3] = { 0, 0, 0 };
        bool finite = true, monotone = true;
        for (int step = 0; step < 16; ++step) {
            v3 pos = { cam.x + dir.x * t, cam.y + dir.y * t,
                       cam.z + dir.z * t };
            float d = cloudDensity(u, pos);
            float stepLen = baseStep;
            if (d > 0.003f) {
                // light march toward the noon sun (0,1,0)
                float sunStep = 36.0f / 4.0f;
                float od = 0.0f;
                for (int j = 0; j < 4; ++j) {
                    v3 lp = { pos.x, pos.y + ((float)j + 0.5f) * sunStep,
                              pos.z };
                    od += cloudDensity(u, lp) * sunStep;
                    if (od > 2.0f) break;
                }
                float shadowT = std::exp(-od * 0.12f);
                float extinction = d * stepLen * 0.12f;
                float alpha = 1.0f - std::exp(-extinction);
                for (int k = 0; k < 3; ++k)
                    acc[k] += alpha * trans;  // colour weights, finite check
                trans *= 1.0f - alpha;
                if (trans > prev_trans + 1e-6f) monotone = false;
                prev_trans = trans;
                if (trans < 0.02f) break;
            } else {
                stepLen = baseStep * 3.0f;  // adaptive stride
            }
            t += stepLen;
            if (t > farD) break;
            if (!std::isfinite(trans) || !std::isfinite(acc[0])
                || !std::isfinite(acc[1]) || !std::isfinite(acc[2]))
                finite = false;
        }
        check(finite, "march accumulators stay finite");
        check(monotone, "transmittance monotonically non-increasing");
        check(trans >= 0.0f && trans <= 1.0f, "transmittance in [0,1]");
        std::printf("      march: transmittance=%.4f, hit-cloud=%s\n",
                    trans, trans < 0.999f ? "yes" : "no");
    }

    // 6. BUG DEMO A: the sunset tint clock ------------------------------------
    // Current shader: fract(gameTime / 24.0) where gameTime is ELAPSED
    // SECONDS - so the "sunset" window cycles every 24 s of play, and the
    // window (0.75..0.92) never fires at the real dusk fraction (0.5).
    {
        std::printf("== sunset tint audit ==\n");
        auto oldTint = [](float f) {
            return ss(0.75f, 0.85f, f) * (1.0f - ss(0.83f, 0.92f, f));
        };
        float t_max = 0.0f;
        int firings = 0;
        bool prev = false;
        for (int t = 0; t <= 60; ++t) {  // one minute of play
            float f = fractf(t / 24.0f);
            float w = oldTint(f);
            t_max = std::max(t_max, w);
            bool on = w > 0.01f;
            if (on && !prev) ++firings;
            prev = on;
        }
        std::printf("      old tint over 60 s of play: peaks at %.2f, "
                    "fires %d separate times\n", t_max, firings);
        check(firings >= 2,
              "old tint pulses multiple times per minute (gameTime/24 bug)");
        float dusk = oldTint(0.5f);   // real dusk: sun at the horizon
        float noon = oldTint(0.25f);
        std::printf("      old tint at real dusk fraction 0.5 -> %.4f, "
                    "at noon fraction 0.25 -> %.4f\n", dusk, noon);
        check(dusk == 0.0f,
              "old tint is ZERO at the actual dusk (window misaligned)");
        // proposed fix: tint from the sun elevation itself
        auto newTint = [](float dayFraction) {
            float sunHeight = (float)std::sin(2.0 * PI_D * dayFraction);
            return 1.0f - ss(0.0f, 0.28f, std::abs(sunHeight));
        };
        check(newTint(0.5f) > 0.9f, "new tint fires at dusk (fraction 0.5)");
        check(newTint(0.0f) > 0.9f, "new tint fires at dawn (fraction 0)");
        check(newTint(0.25f) < 0.05f, "new tint off at noon");
        check(newTint(0.75f) < 0.05f, "new tint off at midnight");
        std::printf("      new tint: dusk=%.3f dawn=%.3f noon=%.3f "
                    "midnight=%.3f\n", newTint(0.5f), newTint(0.0f),
                    newTint(0.25f), newTint(0.75f));
    }

    // 7. BUG DEMO B: reversed smoothstep is spec-undefined --------------------
    {
        std::printf("== smoothstep audit ==\n");
        bool identical = true;
        for (int i = 0; i <= 100; ++i) {
            float h = i / 100.0f;
            float reversed = ss(1.0f, 0.65f, h);  // what drivers compute
            float fixed = 1.0f - ss(0.65f, 1.0f, h);
            if (std::abs(reversed - fixed) > 1e-6f) identical = false;
        }
        check(identical,
              "1-smoothstep(0.65,1,h) equals the reversed-edge intent");
        std::printf("      NOTE: GLSL 1.20 declares smoothstep UNDEFINED for "
                    "edge0 >= edge1;\n      the shader used smoothstep(1.0, "
                    "0.65, height) - fix to the defined form\n");
    }

    std::printf("\nRESULT: %s (%d failures)\n",
                failures ? "RED" : "GREEN", failures);
    return failures ? 1 : 0;
}
