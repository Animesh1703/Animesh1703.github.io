---
name: jmp-spc-analysis
description: Build complete JMP-level statistical process control (SPC) and quality analysis web applications. Use this skill whenever users mention SPC charts, control charts, process capability, Western Electric rules, DOE (design of experiments), Pareto analysis, Gage R&R, MSA (measurement system analysis), process monitoring, quality control, Six Sigma analysis, statistical quality tools, or want to create analysis dashboards for manufacturing/quality data. Also trigger when users ask about reading Excel/CSV data for statistical analysis, calculating control limits, detecting out-of-control points, or building professional statistical analysis interfaces.
---

# JMP Statistical Process Control Analysis Skill

Build complete, professional-grade statistical analysis web applications with JMP-level functionality.

## When To Use This Skill

Trigger automatically when users mention:
- SPC charts, control charts, I-MR charts, X̄-R charts
- Western Electric rules, out-of-control detection
- Process capability, Cpk, Cp, Pp, Ppk
- DOE (Design of Experiments), factorial analysis
- Pareto analysis, 80/20 rule
- Gage R&R, MSA (Measurement System Analysis)
- Quality control, Six Sigma, process monitoring
- Statistical analysis of Excel/CSV manufacturing data

## Core Implementation Requirements

### 1. Excel/CSV Data Reading (CRITICAL)

Always use these libraries:
```html
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/PapaParse/5.4.1/papaparse.min.js"></script>
```

**Critical Pattern - Always Use:**
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
                    processUploadedData();
                }
            });
        };
        reader.readAsText(file);
    } else if (['xlsx', 'xls'].includes(ext)) {
        reader.onload = (e) => {
            const data = new Uint8Array(e.target.result);
            const workbook = XLSX.read(data, { type: 'array' });
            const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
            uploadedData = XLSX.utils.sheet_to_json(firstSheet);
            processUploadedData();
        };
        reader.readAsArrayBuffer(file);
    }
}
```

### 2. Control Limit Calculations

**Standard Formula:**
```javascript
const mean = values.reduce((a, b) => a + b) / values.length;
const variance = values.reduce((sum, v) => sum + Math.pow(v - mean, 2), 0) / (values.length - 1);
const stdDev = Math.sqrt(variance);

const ucl = mean + 3 * stdDev;
const lcl = mean - 3 * stdDev;
```

**Manual Override Support (Phase 2 Monitoring):**
```javascript
const uclManual = parseFloat(document.getElementById('spc_ucl')?.value);
const clManual = parseFloat(document.getElementById('spc_cl')?.value);
const lclManual = parseFloat(document.getElementById('spc_lcl')?.value);

const ucl = !isNaN(uclManual) ? uclManual : mean + 3 * stdDev;
const centerLine = !isNaN(clManual) ? clManual : mean;
const lcl = !isNaN(lclManual) ? lclManual : mean - 3 * stdDev;
```

### 3. Western Electric Rules (All 8 Required)

```javascript
function detectViolations(data, ucl, lcl, mean) {
    const violations = [];
    const sigma = (ucl - mean) / 3;
    
    // Zone definitions
    const zoneAUpper = mean + 2 * sigma;
    const zoneBUpper = mean + sigma;
    const zoneBLower = mean - sigma;
    const zoneALower = mean - 2 * sigma;
    
    for (let i = 0; i < data.length; i++) {
        const point = data[i];
        
        // Rule 1: Beyond 3σ
        if (point > ucl || point < lcl) {
            violations.push({
                point: i + 1,
                rule: 'Rule 1',
                pattern: point > ucl ? 'Upward Spike' : 'Downward Spike',
                severity: 'HIGH',
                cause: 'Special cause - equipment malfunction, operator error',
                action: 'Investigate immediately. Check equipment logs.'
            });
        }
        
        // Rule 2: 9 points same side
        if (i >= 8) {
            const last9 = data.slice(i - 8, i + 1);
            if (last9.every(p => p > mean)) {
                violations.push({
                    point: i + 1,
                    rule: 'Rule 2',
                    pattern: 'Mean Shift Upward',
                    severity: 'MEDIUM'
                });
            }
        }
        
        // Rule 3: 6 points trending
        if (i >= 5) {
            const last6 = data.slice(i - 5, i + 1);
            if (last6.every((p, idx) => idx === 0 || p > last6[idx - 1])) {
                violations.push({
                    point: i + 1,
                    rule: 'Rule 3',
                    pattern: 'Upward Trend',
                    severity: 'MEDIUM'
                });
            }
        }
        
        // Rules 4-8: Implement alternating, zone violations, stratification, mixture
        // [Include all 8 rules in production code]
    }
    
    return violations;
}
```

### 4. Moving Range Chart (Always Include with I-Chart)

```javascript
function calculateMR(data) {
    const mr = [];
    for (let i = 1; i < data.length; i++) {
        mr.push(Math.abs(data[i] - data[i-1]));
    }
    const mrBar = mr.reduce((a, b) => a + b) / mr.length;
    const mrUCL = 3.267 * mrBar;  // D4 constant for n=2
    return { mr, mrBar, mrUCL };
}
```

### 5. Process Capability

```javascript
function calculateCapability(values, lsl, usl, target) {
    const mean = values.reduce((a, b) => a + b) / values.length;
    const variance = values.reduce((sum, v) => sum + Math.pow(v - mean, 2), 0) / (values.length - 1);
    const stdDev = Math.sqrt(variance);

    const cp = (usl - lsl) / (6 * stdDev);
    const cpu = (usl - mean) / (3 * stdDev);
    const cpl = (mean - lsl) / (3 * stdDev);
    const cpk = Math.min(cpu, cpl);

    // Cpm if target provided
    let cpm = null;
    if (target) {
        const tau = Math.sqrt(variance + Math.pow(mean - target, 2));
        cpm = (usl - lsl) / (6 * tau);
    }

    const defects = values.filter(v => v < lsl || v > usl).length;
    const ppm = (defects / values.length) * 1000000;
    const sigmaLevel = cpk * 3;

    return { cp, cpk, cpu, cpl, cpm, ppm, sigmaLevel };
}
```

### 6. CUSUM Chart

```javascript
function calculateCUSUM(data, target) {
    const sigma = Math.sqrt(data.reduce((sum, v) => sum + Math.pow(v - target, 2), 0) / data.length);
    const k = 0.5 * sigma;
    const cusumPos = [0];
    const cusumNeg = [0];
    
    for (let i = 0; i < data.length; i++) {
        cusumPos.push(Math.max(0, cusumPos[i] + data[i] - target - k));
        cusumNeg.push(Math.max(0, cusumNeg[i] - data[i] + target - k));
    }
    
    return { cusumPos: cusumPos.slice(1), cusumNeg: cusumNeg.slice(1), H: 5 * sigma };
}
```

### 7. EWMA Chart

```javascript
function calculateEWMA(data, lambda, target) {
    const ewma = [target];
    for (let i = 0; i < data.length; i++) {
        ewma.push(lambda * data[i] + (1 - lambda) * ewma[i]);
    }
    
    const sigma = Math.sqrt(data.reduce((sum, v) => sum + Math.pow(v - target, 2), 0) / data.length);
    const L = 3;
    const ewmaUCL = target + L * sigma * Math.sqrt(lambda / (2 - lambda));
    const ewmaLCL = target - L * sigma * Math.sqrt(lambda / (2 - lambda));
    
    return { ewma: ewma.slice(1), ewmaUCL, ewmaLCL };
}
```

## Critical Requirements Checklist

**ALWAYS Include:**
- ✅ Real Excel/CSV data reading (XLSX.js + PapaParse)
- ✅ All 8 Western Electric Rules (not just Rule 1)
- ✅ Moving Range chart with I-chart
- ✅ Manual control limit inputs (UCL, CL, LCL)
- ✅ Pattern classification (spike, shift, trend, drift)
- ✅ Chart.js with annotation plugin
- ✅ Color-coded violation points (red=violation, orange=out-of-spec, green=in-control)
- ✅ Detailed violation table with severity badges
- ✅ Professional UI with modern styling

**NEVER Do:**
- ❌ Use hardcoded demo data when user uploads real data
- ❌ Implement only Rule 1 (need all 8)
- ❌ Skip Moving Range chart
- ❌ Forget manual control limit support
- ❌ Use localStorage/sessionStorage (not supported in artifacts)

## Professional UI Pattern

```css
:root {
    --primary: #00ff88;
    --secondary: #ff0066;
    --dark: #0a0e1a;
    --card: #141824;
    --text: #e8e8e8;
    --text-dim: #8892a6;
    --warning: #ffaa00;
}
```

## Chart.js Configuration

```javascript
new Chart(ctx, {
    type: 'line',
    data: {
        labels: values.map((_, i) => i + 1),
        datasets: [{
            data: values,
            backgroundColor: pointColors,  // Red for violations, green for in-control
            pointRadius: pointRadius,      // Larger for violations
            borderWidth: 2
        }]
    },
    options: {
        plugins: {
            annotation: {
                annotations: {
                    ucl: {
                        type: 'line',
                        yMin: ucl, yMax: ucl,
                        borderColor: 'rgba(255, 0, 102, 0.8)',
                        borderDash: [5, 5],
                        label: { display: true, content: `UCL: ${ucl.toFixed(3)}` }
                    }
                    // Add CL, LCL, LSL, USL
                }
            }
        }
    }
});
```

## Pareto Analysis

```javascript
function createParetoChart(categoryData) {
    // Sort by count descending
    const sorted = Object.entries(categoryData).sort((a, b) => b[1] - a[1]);
    const total = sorted.reduce((sum, [_, count]) => sum + count, 0);
    
    // Calculate cumulative percentage
    let cumulative = 0;
    const paretoData = sorted.map(([category, count]) => {
        cumulative += count;
        return {
            category,
            count,
            cumPct: (cumulative / total) * 100
        };
    });
    
    // Find 80% line
    const index80 = paretoData.findIndex(d => d.cumPct >= 80);
    
    // Create chart with bar + line
    // Bars for counts, line for cumulative %
    // Highlight vital few (80% contributors)
}
```

## DOE Main Effects

```javascript
function analyzeDOE(response, factors, data) {
    const effects = [];
    
    for (const factor of factors) {
        const levels = {};
        data.forEach(row => {
            const level = String(row[factor]);
            const value = parseFloat(row[response]);
            if (!levels[level]) levels[level] = [];
            levels[level].push(value);
        });
        
        const levelMeans = {};
        for (const [level, values] of Object.entries(levels)) {
            levelMeans[level] = values.reduce((a, b) => a + b) / values.length;
        }
        
        const means = Object.values(levelMeans);
        const effect = Math.max(...means) - Math.min(...means);
        
        effects.push({ factor, effect, levelMeans });
    }
    
    return effects.sort((a, b) => Math.abs(b.effect) - Math.abs(a.effect));
}
```

## Common User Patterns

**"Add MR chart"** → Include calculateMR() and display below I-chart
**"Show CUSUM/EWMA options"** → Add toggle buttons for chart types
**"Tell me which rule violated"** → Include rule number + pattern in violation table
**"Manual control limits"** → Add UCL/CL/LCL input fields with Phase 2 explanation
**"Not reading my Excel"** → Verify XLSX.js config and column detection

## Reference Architecture

Create single-file HTML with:
1. Upload zone (drag/drop + file picker)
2. Column dropdowns (auto-populated from uploaded file)
3. Input fields (LSL, USL, target, manual limits)
4. Analysis button
5. Results section (stats cards, charts, violation table)
6. Professional cyberpunk styling

## Testing Before Delivery

Verify:
- [ ] Excel/CSV upload works
- [ ] Columns auto-populate
- [ ] Charts show real data (not demo)
- [ ] UCL/LCL calculated correctly
- [ ] All 8 Western Electric rules detect violations
- [ ] MR chart displays
- [ ] Manual limits override auto-calculation
- [ ] Violations highlighted in red
- [ ] Pattern classification works
- [ ] No console errors
