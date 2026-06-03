# Thin Film SPC Analyzer

A browser-based Statistical Process Control platform for PECVD, CVD, PVD, and ALD thin film deposition processes. Upload your wafer run data and get instant process analysis — no server, no installation, no data leaves your browser.

🔗 **[Live App](https://animeshthakre.github.io/thin-film-spc-analyzer/)**

---

## Features

| Module | What it does |
|---|---|
| **SPC Charts** | I-Chart, MR, CUSUM, EWMA, Xbar-R with 1σ/2σ/3σ zones and Western Electric rules |
| **Capability Analysis** | Cp, Cpk, Pp, Ppk, Sigma Level, PPM — fully editable with bidirectional solver |
| **DOE** | Main effects + Full/Fractional Factorial with user-defined factor levels |
| **Root Cause Analysis** | Fishbone diagram, failed run isolation, factor deviation comparison |
| **File Comparison** | Overlay Before vs After OOC profiles side by side |
| **Wafer Map** | Spatial site visualization with non-uniformity trending |
| **Trend & Forecast** | Drift detection, runs-to-limit-breach, Cpk tightening recommendations |
| **FMEA** | Standalone risk table with live RPN scoring and CSV export |
| **Tools & Chambers** | Per-tool and per-chamber Cpk, sigma, and violation breakdown |

---

## How to use

1. Download `index.html`
2. Open it in any modern browser (Chrome, Firefox, Edge)
3. Upload a CSV or Excel file with your wafer run data
4. Set USL / LSL for your primary parameter
5. Explore all tabs

### Expected data format

| Column | Description |
|---|---|
| `Wafer_ID` | Wafer identifier |
| `Tool_ID` | Equipment ID (optional — enables tool comparison) |
| `Chamber_ID` | Chamber ID (optional) |
| `Film_Thickness_A` | Primary measurement (Å) |
| `Temperature_C`, `Pressure_mTorr`, `RF_Power_W` | Process inputs |
| `Uniformity_pct`, `Refractive_Index` | Film properties |
| `Defect_Density`, `Yield_pct` | Quality outputs |

Any numeric columns are automatically detected. Column names are flexible.

---

## Editable values

Every spec limit (USL, LSL, Target) is independently editable per parameter. Change any value and all capability indices, control limits, violations, and SPC lines update instantly across all tabs.

Reverse calculation: type a target Cpk → the app solves for the required σ reduction and shows which process levers to tighten.

---

## Built with

- [Chart.js](https://www.chartjs.org/) — charts and visualizations
- [PapaParse](https://www.papaparse.com/) — CSV parsing
- [SheetJS](https://sheetjs.com/) — Excel file reading
- [chartjs-plugin-zoom](https://www.chartjs.org/chartjs-plugin-zoom/) — zoom and pan
- Vanilla JavaScript — no frameworks, no build step

---

## About

Built by **Animesh Thakre** — MS Chemical Engineering, University of Dayton.

Developed as a portfolio project combining domain expertise in thin film process engineering (SPC, DOE, FMEA, capability analysis) with AI-assisted software development.

📧 thakrea3@udayton.edu  
🔗 [LinkedIn](https://www.linkedin.com/in/animesh-thakre)

---

## License

MIT — free to use, modify, and share.
