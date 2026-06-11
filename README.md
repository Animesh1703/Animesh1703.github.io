---
name: jmp-spc-analysis
description: Build complete JMP-level statistical process control (SPC) and quality analysis web applications. Use this skill whenever users mention SPC charts, control charts, process capability, Western Electric rules, DOE (design of experiments), Pareto analysis, Gage R&R, MSA (measurement system analysis), process monitoring, quality control, Six Sigma analysis, statistical quality tools, correlation analysis, input-output relationships, or want to create analysis dashboards for manufacturing/quality data. Also trigger when users ask about reading Excel/CSV data for statistical analysis, calculating control limits, detecting out-of-control points, distribution analysis, skewness detection, or building professional statistical analysis interfaces.
---

# JMP Statistical Process Control Analysis Skill

Build complete, professional-grade statistical analysis web applications with JMP-level functionality. This skill captures everything needed to create working SPC, capability, DOE, correlation, and quality analysis tools.

---

## ⚠️ CRITICAL RULES — Read Before Writing Any Code

These rules fix known bugs found through comparative analysis and Apify-verified best practices.

### Rule 1 — NEVER embed or hardcode data
Always read from the uploaded file. Never fabricate failure notes, root causes, or categorical field values.

```javascript
// ✅ CORRECT — read from file, display as-is
failRows.forEach(r => {
    td.textContent = r['Issue_Notes'] ?? '—';  // exact string from file
});

// ❌ WRONG — invented text not in the file
td.textContent = "Chamber contamination";
```

### Rule 2 — Use σ_within (MR-based) for I-chart limits, NOT overall std
I-chart UCL/LCL must use within-subgroup sigma estimated from the moving range. Overall sample std conflates short-term and long-term variation and produces inflated control limits.

```javascript
// ✅ CORRECT — σ_within from moving range
function calcSigmaWithin(values) {
    const mr = values.slice(1).map((v, i) => Math.abs(v - values[i]));
    const mrBar = mr.reduce((a, b) => a + b, 0) / mr.length;
    return mrBar / 1.128;  // d₂ constant for n=2
}
const sigmaW = calcSigmaWithin(values);
const ucl = mean + 3 * sigmaW;
const lcl = mean - 3 * sigmaW;

// ❌ WRONG — inflated limits, mixes short/long-term variation
const ucl = mean + 3 * stdDev;  // stdDev from sample variance
```

### Rule 3 — Cp/Cpk use σ_within; Pp/Ppk use σ_overall — NEVER equate them
- **Cp/Cpk** = potential/short-term capability → uses **σ_within** (MR-based sigma estimator)
- **Pp/Ppk** = actual/long-term performance → uses **σ_overall** (sample std dev)
- Setting `pp = cp` is a bug. They will differ whenever the process has long-term variation.

```javascript
// ✅ CORRECT — separate sigma sources
function calculateCapability(values, lsl, usl, target) {
    const n = values.length;
    const mean = values.reduce((a, b) => a + b) / n;

    // σ_overall for Pp/Ppk (long-term performance)
    const sigmaOverall = Math.sqrt(
        values.reduce((s, v) => s + (v - mean) ** 2, 0) / (n - 1)
    );

    // σ_within for Cp/Cpk (short-term capability, MR-based)
    const mr = values.slice(1).map((v, i) => Math.abs(v - values[i]));
    const sigmaWithin = (mr.reduce((a, b) => a + b) / mr.length) / 1.128;

    // Short-term capability (uses σ_within)
    const cp  = (usl - lsl) / (6 * sigmaWithin);
    const cpu = (usl - mean) / (3 * sigmaWithin);
    const cpl = (mean - lsl) / (3 * sigmaWithin);
    const cpk = Math.min(cpu, cpl);

    // Long-term performance (uses σ_overall)
    const pp  = (usl - lsl) / (6 * sigmaOverall);
    const ppu = (usl - mean) / (3 * sigmaOverall);
    const ppl = (mean - lsl) / (3 * sigmaOverall);
    const ppk = Math.min(ppu, ppl);

    // Cpm (if target provided)
    let cpm = null;
    if (target !== null) {
        const tau = Math.sqrt(sigmaOverall ** 2 + (mean - target) ** 2);
        cpm = (usl - lsl) / (6 * tau);
    }

    // Theoretical PPM via normal CDF (not just count-based)
    function normCDF(z) {
        const t = 1 / (1 + 0.2316419 * Math.abs(z));
        const d = 0.3989423 * Math.exp(-z * z / 2);
        const p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.7814779 + t * (-1.8212560 + t * 1.3302744))));
        return z > 0 ? 1 - p : p;
    }
    const ppmTheoretical = (normCDF((lsl - mean) / sigmaOverall) + (1 - normCDF((usl - mean) / sigmaOverall))) * 1e6;

    // Observed PPM
    const defects = values.filter(v => v < lsl || v > usl).length;
    const ppmObserved = (defects / n) * 1e6;

    const sigmaLevel = cpk * 3;

    return { cp, cpk, cpu, cpl, pp, ppk, ppu, ppl, cpm,
             ppmTheoretical, ppmObserved, sigmaLevel,
             sigmaWithin, sigmaOverall, mean };
}
```

### Rule 4 — NEVER hardcode sigma in CUSUM/EWMA — derive from data

```javascript
// ✅ CORRECT — sigma from MR-based σ_within
function calculateCUSUM(data, target) {
    const mr = data.slice(1).map((v, i) => Math.abs(v - data[i]));
    const sigma = (mr.reduce((a, b) => a + b) / mr.length) / 1.128;
    const k = 0.5 * sigma;
    const H = 5 * sigma;
    const cusumPos = [0], cusumNeg = [0];
    for (let i = 0; i < data.length; i++) {
        const dev = data[i] - target;
        cusumPos.push(Math.max(0, cusumPos.at(-1) + dev - k));
        cusumNeg.push(Math.max(0, cusumNeg.at(-1) - dev - k));
    }
    return { cusumPos: cusumPos.slice(1), cusumNeg: cusumNeg.slice(1), H, sigma };
}

function calculateEWMA(data, lambda, target) {
    const mr = data.slice(1).map((v, i) => Math.abs(v - data[i]));
    const sigma = (mr.reduce((a, b) => a + b) / mr.length) / 1.128;
    const L = 3;
    const ewma = [target];
    for (const x of data) ewma.push(lambda * x + (1 - lambda) * ewma.at(-1));
    const ewmaUCL = target + L * sigma * Math.sqrt(lambda / (2 - lambda));
    const ewmaLCL = target - L * sigma * Math.sqrt(lambda / (2 - lambda));
    return { ewma: ewma.slice(1), ewmaUCL, ewmaLCL };
}

// ❌ WRONG — hardcoded sigma=0.5 is arbitrary, gives wrong limits
const sigma = 0.5;
```

### Rule 5 — Implement ALL 8 Western Electric Rules (not just Rule 1)

```javascript
function detectViolations(data, ucl, lcl, mean) {
    const violations = [];
    const sigma = (ucl - mean) / 3;
    const zA2 = mean + 2 * sigma, zA1 = mean - 2 * sigma;  // Zone A boundaries
    const zB2 = mean + sigma,     zB1 = mean - sigma;       // Zone B boundaries

    for (let i = 0; i < data.length; i++) {
        const p = data[i];

        // Rule 1: Beyond 3σ
        if (p > ucl || p < lcl) {
            violations.push({ point: i+1, value: p, rule: 'Rule 1',
                description: 'One point beyond 3σ', pattern: p > ucl ? 'Upward Spike' : 'Downward Spike',
                severity: 'HIGH', cause: 'Equipment malfunction, operator error, measurement error',
                action: 'Investigate immediately. Check equipment logs, verify measurements.' });
        }

        // Rule 2: 9 consecutive points same side of centerline
        if (i >= 8) {
            const s = data.slice(i-8, i+1);
            const dir = s.every(x => x > mean) ? 'Upward' : s.every(x => x < mean) ? 'Downward' : null;
            if (dir) violations.push({ point: i+1, value: p, rule: 'Rule 2',
                description: '9 consecutive points same side', pattern: `Mean Shift ${dir}`,
                severity: 'MEDIUM', cause: 'Sustained shift: new material, operator change, calibration drift',
                action: 'Identify cause. If acceptable, recalculate control limits.' });
        }

        // Rule 3: 6 consecutive points trending
        if (i >= 5) {
            const s = data.slice(i-5, i+1);
            const up = s.every((x, j) => j === 0 || x > s[j-1]);
            const dn = s.every((x, j) => j === 0 || x < s[j-1]);
            if (up || dn) violations.push({ point: i+1, value: p, rule: 'Rule 3',
                description: `6 consecutive points ${up ? 'increasing' : 'decreasing'}`,
                pattern: up ? 'Upward Trend' : 'Downward Trend', severity: 'MEDIUM',
                cause: up ? 'Tool wear, temperature increase, gradual buildup' : 'Tool improvement, cooling',
                action: 'Identify trending cause before limits exceeded.' });
        }

        // Rule 4: 14 consecutive points alternating up/down
        if (i >= 13) {
            const s = data.slice(i-13, i+1);
            const alt = s.every((x, j) => j === 0 || (j % 2 === 0 ? x < s[j-1] : x > s[j-1])) ||
                        s.every((x, j) => j === 0 || (j % 2 === 0 ? x > s[j-1] : x < s[j-1]));
            if (alt) violations.push({ point: i+1, value: p, rule: 'Rule 4',
                description: '14 consecutive points alternating', pattern: 'Oscillation',
                severity: 'LOW', cause: 'Two alternating process streams, over-adjustment',
                action: 'Check for multiple process streams or operator over-correction.' });
        }

        // Rule 5: 2 of 3 consecutive points in Zone A (beyond 2σ same side)
        if (i >= 2) {
            const s = data.slice(i-2, i+1);
            const inZoneAUp = s.filter(x => x > zA2).length;
            const inZoneADn = s.filter(x => x < zA1).length;
            if (inZoneAUp >= 2 || inZoneADn >= 2) violations.push({ point: i+1, value: p, rule: 'Rule 5',
                description: '2 of 3 points in Zone A (beyond 2σ)', pattern: 'Zone A Warning',
                severity: 'MEDIUM', cause: 'Potential shift; process approaching control limit',
                action: 'Monitor closely. Prepare for possible intervention.' });
        }

        // Rule 6: 4 of 5 consecutive points in Zone B or beyond (beyond 1σ same side)
        if (i >= 4) {
            const s = data.slice(i-4, i+1);
            const inBUp = s.filter(x => x > zB2).length;
            const inBDn = s.filter(x => x < zB1).length;
            if (inBUp >= 4 || inBDn >= 4) violations.push({ point: i+1, value: p, rule: 'Rule 6',
                description: '4 of 5 points in Zone B or beyond (beyond 1σ)', pattern: 'Gradual Shift',
                severity: 'MEDIUM', cause: 'Gradual drift: material change, wear, environment',
                action: 'Trend analysis recommended. Identify drift source.' });
        }

        // Rule 7: 15 consecutive points in Zone C (within 1σ of centerline — stratification)
        if (i >= 14) {
            const s = data.slice(i-14, i+1);
            if (s.every(x => x > zB1 && x < zB2)) violations.push({ point: i+1, value: p, rule: 'Rule 7',
                description: '15 consecutive points within Zone C', pattern: 'Stratification',
                severity: 'LOW', cause: 'Mixed or stratified samples, incorrect rational subgrouping',
                action: 'Review sampling strategy. Check for mixed process streams.' });
        }

        // Rule 8: 8 consecutive points beyond Zone C on both sides (mixture)
        if (i >= 7) {
            const s = data.slice(i-7, i+1);
            if (s.every(x => x > zB2 || x < zB1)) violations.push({ point: i+1, value: p, rule: 'Rule 8',
                description: '8 consecutive points beyond Zone C', pattern: 'Mixture',
                severity: 'MEDIUM', cause: 'Two distinct process streams plotted together',
                action: 'Separate data by source (machine, operator, shift, material).' });
        }
    }

    return violations;
}
```

### Rule 6 — DOE effects must be signed and include interactions

```javascript
// ✅ CORRECT — signed main effects + interaction
function calcDOE(data, factorA, factorB, response) {
    const hi = v => v >= (Math.max(...v) + Math.min(...v)) / 2;
    const rows = data.filter(r => r[factorA] != null && r[factorB] != null && r[response] != null);

    const mainA = rows.filter(r => hi(rows.map(x => x[factorA]))(r[factorA]))
                      .reduce((s, r) => s + r[response], 0) /
                  rows.filter(r => hi(rows.map(x => x[factorA]))(r[factorA])).length -
                  rows.filter(r => !hi(rows.map(x => x[factorA]))(r[factorA]))
                      .reduce((s, r) => s + r[response], 0) /
                  rows.filter(r => !hi(rows.map(x => x[factorA]))(r[factorA])).length;
    // mainB and interaction follow same pattern
    // Effect CAN be negative — that is physically meaningful (e.g., higher pressure → lower etch rate)
    return { mainA, /* mainB, interaction */ };
}
```

### Rule 7 — Always compute and display skewness; warn if |skew| > 1.5

```javascript
function computeSkewness(values) {
    const n = values.length;
    const mean = values.reduce((a, b) => a + b) / n;
    const std = Math.sqrt(values.reduce((s, v) => s + (v - mean) ** 2, 0) / (n - 1));
    const skew = values.reduce((s, v) => s + ((v - mean) / std) ** 3, 0) * n / ((n-1) * (n-2));
    return skew;
}
// In display:
const skew = computeSkewness(values);
if (Math.abs(skew) > 1.5) {
    showWarning(`Skewness = ${skew.toFixed(2)}. Non-normal distribution detected. 
    Normal-theory control limits may be inappropriate. Consider log or Box-Cox transformation.`);
}
```

---

## Core Capabilities

### 1. Complete SPC Charts
- **I-MR Charts** (Individuals & Moving Range) — always use σ_within for limits
- **X̄-R Charts** (Average & Range)
- **X̄-S Charts** (Average & Standard Deviation)
- **Attribute Charts** (P, NP, C, U charts)
- **CUSUM & EWMA** — sigma always derived from data, never hardcoded

### 2. Western Electric Rules — All 8 Required
| Rule | Pattern | Sensitivity |
|------|---------|-------------|
| 1 | 1 point beyond 3σ | HIGH |
| 2 | 9 points same side | MEDIUM |
| 3 | 6 points trending | MEDIUM |
| 4 | 14 points alternating | LOW |
| 5 | 2/3 in Zone A | MEDIUM |
| 6 | 4/5 in Zone B | MEDIUM |
| 7 | 15 in Zone C (stratification) | LOW |
| 8 | 8 beyond Zone C (mixture) | MEDIUM |

### 3. Process Capability
- **Cp/Cpk** — short-term, σ_within (MR-based)
- **Pp/Ppk** — long-term, σ_overall (sample std)
- **Cpm** — when target ≠ mean
- **Theoretical PPM** via normCDF (not just count)
- **Observed PPM** from actual data
- **Sigma level** = Cpk × 3

### 4. Additional Analyses
- **Correlation tab** — Pearson r for all numeric inputs vs. response (bar chart sorted by |r|)
- **DOE** — signed main effects + interaction terms
- **Pareto** — 80/20 rule, vital few
- **Distribution** — skewness, normality check, histogram + normal overlay
- **MSA/Gage R&R** — measurement system analysis

---

## Implementation Pattern

### File Structure (Single HTML File)

```html
<!DOCTYPE html>
<html>
<head>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/PapaParse/5.4.1/papaparse.min.js"></script>
</head>
```

### Critical Data Reading Pattern

```javascript
let uploadedData = null;

function handleFile(file) {
    const ext = file.name.split('.').pop().toLowerCase();
    const reader = new FileReader();

    if (ext === 'csv') {
        reader.onload = (e) => {
            Papa.parse(e.target.result, {
                header: true,
                dynamicTyping: true,
                complete: (results) => {
                    uploadedData = results.data.filter(row =>
                        Object.values(row).some(v => v !== null && v !== '')
                    );
                    processUploadedData(file);
                }
            });
        };
        reader.readAsText(file);
    } else if (['xlsx', 'xls'].includes(ext)) {
        reader.onload = (e) => {
            const data = new Uint8Array(e.target.result);
            const workbook = XLSX.read(data, { type: 'array' });
            const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
            uploadedData = XLSX.utils.sheet_to_json(firstSheet).filter(row =>
                Object.values(row).some(v => v !== null && v !== '')
            );
            processUploadedData(file);
        };
        reader.readAsArrayBuffer(file);
    }
}
```

### Moving Range Chart (Always Include with I-Chart)

```javascript
function calculateMR(data) {
    const mr = data.slice(1).map((v, i) => Math.abs(v - data[i]));
    const mrBar = mr.reduce((a, b) => a + b) / mr.length;
    const mrUCL = 3.267 * mrBar;  // D4 constant for n=2
    return { mr, mrBar, mrUCL };
}
```

### Manual Control Limits Override (Phase 2)

```javascript
const uclManual = parseFloat(document.getElementById('spc_ucl')?.value);
const clManual  = parseFloat(document.getElementById('spc_cl')?.value);
const lclManual = parseFloat(document.getElementById('spc_lcl')?.value);

const ucl = !isNaN(uclManual) ? uclManual : mean + 3 * sigmaWithin;
const cl  = !isNaN(clManual)  ? clManual  : mean;
const lcl = !isNaN(lclManual) ? lclManual : mean - 3 * sigmaWithin;
```

### Correlation Analysis Tab

```javascript
function pearsonR(xs, ys) {
    const n = xs.length;
    const mx = xs.reduce((a, b) => a + b) / n;
    const my = ys.reduce((a, b) => a + b) / n;
    const num = xs.reduce((s, x, i) => s + (x - mx) * (ys[i] - my), 0);
    const den = Math.sqrt(
        xs.reduce((s, x) => s + (x - mx) ** 2, 0) *
        ys.reduce((s, y) => s + (y - my) ** 2, 0)
    );
    return den === 0 ? 0 : num / den;
}
// Display: horizontal bar chart of all numeric columns vs. response, sorted by |r|, colored by sign
```

---

## UI/UX Color Scheme

```css
:root {
    --primary:  #00ff88;   /* Success / in-control */
    --secondary:#ff0066;   /* Error / violation */
    --dark:     #0a0e1a;
    --card:     #141824;
    --text:     #e8e8e8;
    --text-dim: #8892a6;
    --warning:  #ffaa00;
    --info:     #00aaff;
}
```

### Stat Cards

```html
<div class="stat-grid">
    <div class="stat-card">
        <div class="stat-label">Cp (short-term)</div>
        <div class="stat-value" id="cp-val">—</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Pp (long-term)</div>
        <div class="stat-value" id="pp-val">—</div>
    </div>
    <!-- UCL, CL, LCL, Cpk, Ppk, PPM Theoretical, PPM Observed, Sigma Level -->
</div>
```

### Violation Table

```html
<table class="violation-table">
    <thead>
        <tr>
            <th>Point #</th><th>Value</th><th>Rule</th>
            <th>Pattern</th><th>Severity</th><th>Recommended Action</th>
        </tr>
    </thead>
    <tbody id="violations-body"></tbody>
</table>
```

---

## Multi-Tab Application Structure

For complete suites (7 tabs):

```html
<div class="tabs">
    <div class="tab active"  onclick="switchTab('overview')">📊 Overview</div>
    <div class="tab"         onclick="switchTab('spc')">📈 SPC</div>
    <div class="tab"         onclick="switchTab('capability')">🎯 Capability</div>
    <div class="tab"         onclick="switchTab('correlation')">🔗 Correlation</div>
    <div class="tab"         onclick="switchTab('doe')">🧪 DOE</div>
    <div class="tab"         onclick="switchTab('pareto')">📊 Pareto</div>
    <div class="tab"         onclick="switchTab('rca')">🔍 RCA/Failures</div>
</div>
```

---

## ALWAYS Include

1. **Real file reading** — never hardcoded demo data
2. **Column auto-detection** — populate all dropdowns from uploaded file
3. **σ_within for I-chart** — MR-based, d₂ = 1.128
4. **Cp/Cpk AND Pp/Ppk** — separate, using σ_within vs σ_overall respectively
5. **Signed DOE effects** — can be negative (physically meaningful)
6. **Correlation tab** — Pearson r bar chart for multi-input data
7. **Skewness check** — warn when |skew| > 1.5
8. **All 8 Western Electric rules** — complete detection
9. **Theoretical + Observed PPM** — normCDF-based theoretical
10. **MR chart** — always below I-chart
11. **Manual control limits** — Phase 2 override inputs
12. **Error handling** — try/catch with user-friendly messages

## NEVER Do

1. Don't hardcode or fabricate data values — read from uploaded file
2. Don't use overall std for I-chart limits — use MR-based σ_within
3. Don't set `pp = cp` — they use different sigma sources
4. Don't hardcode sigma = 0.5 in CUSUM/EWMA — derive from data
5. Don't skip MR chart with I-chart
6. Don't implement only Rule 1 — implement all 8 WE rules
7. Don't omit correlation tab on multi-input datasets
8. Don't show DOE effects without their sign (negative effects are valid)
9. Don't skip skewness check
10. Don't use localStorage/sessionStorage in artifacts (not supported)
11. Don't create separate CSS/JS files — single HTML only

---

## Updated Testing Checklist

Before delivering, verify:
- [ ] File upload works for .csv, .xlsx, .xls
- [ ] Columns auto-populate in all dropdowns
- [ ] I-chart limits use σ_within (MR/d₂=1.128), not sample std
- [ ] Cp/Cpk and Pp/Ppk are **different values** (not equal)
- [ ] Theoretical PPM computed via normCDF
- [ ] CUSUM/EWMA sigma derived from data (not hardcoded 0.5)
- [ ] DOE main effects have correct sign (can be negative)
- [ ] Correlation tab shows all numeric inputs vs. response
- [ ] Skewness computed and non-normality warned when |skew| > 1.5
- [ ] All 8 Western Electric rules implemented
- [ ] MR chart displays below I-chart
- [ ] Manual control limits override auto-calculation
- [ ] RCA/Failure tab reads issue notes from actual file (no invented text)
- [ ] No console errors

---

## Reference Architectures

- **Single-focus** → `jmp-analysis-app.html` (SPC monitoring only)
  Best for daily SPC; has all WE rules, MR/CUSUM/EWMA, manual limits

- **Multi-module suite** → `jmp-complete-pro.html` (7 tabs)
  Overview + SPC + Capability + Correlation + DOE + Pareto + RCA

Choose by scope:
- Single analysis type → single-focus app
- Multiple analysis types or multi-input data → multi-module suite
