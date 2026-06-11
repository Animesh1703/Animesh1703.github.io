"""
Thin Film SPC Analyzer — Python Backend
All heavy computation (numpy/scipy) runs here; frontend just renders JSON.
"""

import os
import uuid
import io

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, template_folder="templates")

# Simple in-memory session store  { token: dataframe }
_store: dict[str, pd.DataFrame] = {}

MAX_CHART_POINTS = 2000  # Cap decimated chart arrays for Chart.js performance

# ─── MATH HELPERS (numpy-vectorised, handle 50 k points easily) ─────────────

def _vals(df: pd.DataFrame, col: str) -> np.ndarray:
    return pd.to_numeric(df[col], errors="coerce").dropna().values.astype(float)

def _numeric_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns
            if pd.to_numeric(df[c], errors="coerce").dropna().shape[0] >= 10]

def _avg(a: np.ndarray) -> float:
    return float(np.mean(a)) if len(a) else 0.0

def _std(a: np.ndarray) -> float:
    return float(np.std(a, ddof=1)) if len(a) >= 2 else 0.0

def _sigma_w(a: np.ndarray) -> float:
    """Short-term sigma via average moving range."""
    if len(a) < 2:
        return 0.0
    return float(np.mean(np.abs(np.diff(a))) / 1.128)

def _skew(a: np.ndarray) -> float:
    return float(scipy_stats.skew(a)) if len(a) >= 3 else 0.0

def _pearson(xs: np.ndarray, ys: np.ndarray) -> float:
    n = min(len(xs), len(ys))
    if n < 2:
        return 0.0
    r = np.corrcoef(xs[:n], ys[:n])[0, 1]
    return float(r) if not np.isnan(r) else 0.0

def _decimate(a: np.ndarray, max_pts: int = MAX_CHART_POINTS):
    """Return (decimated_list, label_list, step)."""
    n = len(a)
    if n <= max_pts:
        return a.tolist(), list(range(1, n + 1)), 1
    step = n // max_pts
    idx = np.arange(0, n, step)
    if idx[-1] != n - 1:
        idx = np.append(idx, n - 1)
    return a[idx].tolist(), (idx + 1).tolist(), int(step)

def _r(v):
    """Round float to 6 dp, pass None through."""
    if v is None:
        return None
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
        return None
    return round(float(v), 6)

def _cap(vals: np.ndarray, usl=None, lsl=None, target=None) -> dict:
    m = _avg(vals)
    sw = _sigma_w(vals)
    so = _std(vals)

    cp   = (usl - lsl) / (6 * sw)  if (usl and lsl and sw > 0) else None
    cpu  = (usl - m)   / (3 * sw)  if (usl       and sw > 0) else None
    cpl  = (m   - lsl) / (3 * sw)  if (lsl       and sw > 0) else None
    cpk  = min(x for x in [cpu, cpl] if x is not None) if any(x is not None for x in [cpu, cpl]) else None

    pp   = (usl - lsl) / (6 * so)  if (usl and lsl and so > 0) else None
    ppu  = (usl - m)   / (3 * so)  if (usl       and so > 0) else None
    ppl  = (m   - lsl) / (3 * so)  if (lsl       and so > 0) else None
    ppk  = min(x for x in [ppu, ppl] if x is not None) if any(x is not None for x in [ppu, ppl]) else None

    ppm_t = None
    if usl and lsl and so > 0:
        ppm_t = (scipy_stats.norm.cdf((lsl - m) / so) +
                 (1 - scipy_stats.norm.cdf((usl - m) / so))) * 1e6

    oos = ((vals > usl) if usl else np.zeros(len(vals), bool)) | \
          ((vals < lsl) if lsl else np.zeros(len(vals), bool))
    ppm_o = float(np.sum(oos) / max(len(vals), 1)) * 1e6

    return {k: _r(v) for k, v in {
        "mean": m, "sw": sw, "so": so,
        "cp": cp, "cpk": cpk, "cpu": cpu, "cpl": cpl,
        "pp": pp, "ppk": ppk, "ppu": ppu, "ppl": ppl,
        "ppm_t": ppm_t, "ppm_o": ppm_o,
        "sigma_level": cpk * 3 if cpk else None,
        "skewness": _skew(vals),
    }.items()}


def _violations(vals: np.ndarray, ucl: float, lcl: float, mean: float,
                rules=None) -> list[dict]:
    """Fully-vectorised Western Electric rules — handles 50 k points in ~5 ms."""
    if rules is None:
        rules = {"r1": True, "r2": True, "r3": True, "r5": True}
    sw = (ucl - mean) / 3
    za2_up, za2_dn = mean + 2 * sw, mean - 2 * sw
    n = len(vals)
    vios: list[dict] = []

    # ── Rule 1: beyond ±3σ ───────────────────────────────────────────────────
    if rules.get("r1"):
        idx_up = np.where(vals > ucl)[0]
        idx_dn = np.where(vals < lcl)[0]
        for i in idx_up:
            vios.append({"point": int(i + 1), "value": float(vals[i]), "rule": "Rule 1",
                "desc": "Beyond 3σ", "pattern": "Upward spike", "severity": "HIGH",
                "cause": "Equipment fault, pressure spike, gas flow anomaly",
                "action": "Check tool logs immediately"})
        for i in idx_dn:
            vios.append({"point": int(i + 1), "value": float(vals[i]), "rule": "Rule 1",
                "desc": "Beyond 3σ", "pattern": "Downward spike", "severity": "HIGH",
                "cause": "Equipment fault, pressure spike, gas flow anomaly",
                "action": "Check tool logs immediately"})

    # ── Rule 2: 9 consecutive points same side of mean ───────────────────────
    if rules.get("r2"):
        above = (vals > mean).astype(np.int8)
        below = (vals < mean).astype(np.int8)
        # sliding window sum via cumsum trick (O(n))
        win = 9
        ca = np.cumsum(np.concatenate(([0], above)))
        cb = np.cumsum(np.concatenate(([0], below)))
        run_above = ca[win:] - ca[:-win]   # sum of 'above' in each 9-window
        run_below = cb[win:] - cb[:-win]
        for i in np.where(run_above == win)[0]:
            idx = int(i + win - 1)  # last point in the run (0-based)
            vios.append({"point": idx + 1, "value": float(vals[idx]), "rule": "Rule 2",
                "desc": "9 pts above mean", "pattern": "Mean shift up", "severity": "MEDIUM",
                "cause": "Chamber buildup, gas depletion",
                "action": "Recalibrate flows; consider chamber clean"})
        for i in np.where(run_below == win)[0]:
            idx = int(i + win - 1)
            vios.append({"point": idx + 1, "value": float(vals[idx]), "rule": "Rule 2",
                "desc": "9 pts below mean", "pattern": "Mean shift down", "severity": "MEDIUM",
                "cause": "RF power drift, pressure decrease",
                "action": "Verify RF calibration"})

    # ── Rule 3: 6 consecutive monotone points ────────────────────────────────
    if rules.get("r3"):
        d = np.sign(np.diff(vals)).astype(np.int8)  # +1, 0, -1
        win = 5  # 6 pts → 5 diffs
        cd_up = np.cumsum(np.concatenate(([0], (d == 1).astype(np.int8))))
        cd_dn = np.cumsum(np.concatenate(([0], (d == -1).astype(np.int8))))
        run_up = cd_up[win:] - cd_up[:-win]
        run_dn = cd_dn[win:] - cd_dn[:-win]
        for i in np.where(run_up == win)[0]:
            idx = int(i + win)  # last point of the 6 (0-based in vals)
            vios.append({"point": idx + 1, "value": float(vals[idx]), "rule": "Rule 3",
                "desc": "6 pts trending up", "pattern": "Upward trend", "severity": "MEDIUM",
                "cause": "Tool wear, temperature creep",
                "action": "Schedule preventive maintenance"})
        for i in np.where(run_dn == win)[0]:
            idx = int(i + win)
            vios.append({"point": idx + 1, "value": float(vals[idx]), "rule": "Rule 3",
                "desc": "6 pts trending down", "pattern": "Downward trend", "severity": "MEDIUM",
                "cause": "Precursor depletion",
                "action": "Check gas delivery"})

    # ── Rule 5: 2 of 3 consecutive points in Zone A (beyond ±2σ) ─────────────
    if rules.get("r5"):
        in_za_up = (vals > za2_up).astype(np.int8)
        in_za_dn = (vals < za2_dn).astype(np.int8)
        win = 3
        cu = np.cumsum(np.concatenate(([0], in_za_up)))
        cl = np.cumsum(np.concatenate(([0], in_za_dn)))
        run_zu = cu[win:] - cu[:-win]
        run_zd = cl[win:] - cl[:-win]
        hit = np.where((run_zu >= 2) | (run_zd >= 2))[0]
        for i in hit:
            idx = int(i + win - 1)
            vios.append({"point": idx + 1, "value": float(vals[idx]), "rule": "Rule 5",
                "desc": "2 of 3 in Zone A", "pattern": "Near-limit cluster", "severity": "MEDIUM",
                "cause": "Sudden process shift",
                "action": "Investigate recent process changes"})

    vios.sort(key=lambda x: x["point"])
    return vios


def _linreg(xs: np.ndarray, ys: np.ndarray):
    mx, my = np.mean(xs), np.mean(ys)
    denom = float(np.sum((xs - mx) ** 2))
    slope = float(np.sum((xs - mx) * (ys - my))) / max(denom, 1e-12)
    return slope, float(my - slope * mx)


# ─── ROUTES ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("templates", "index.html")


@app.route("/api/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    ext = f.filename.rsplit(".", 1)[-1].lower()
    try:
        if ext == "csv":
            df = pd.read_csv(f)
        elif ext in ("xlsx", "xls"):
            df = pd.read_excel(f)
        else:
            return jsonify({"error": "Unsupported format — use CSV or XLSX"}), 400
        df = df.dropna(how="all").reset_index(drop=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    num_cols = _numeric_cols(df)
    if not num_cols:
        return jsonify({"error": "No numeric columns detected"}), 400

    primary = next((c for c in num_cols
                    if any(kw in c.lower() for kw in ("thick", "film", "dep", "rate"))),
                   num_cols[0])
    v = _vals(df, primary)
    m, s = _avg(v), _std(v)

    token = str(uuid.uuid4())
    _store[token] = df

    return jsonify({
        "token": token,
        "filename": f.filename,
        "rows": len(df),
        "all_cols": list(df.columns),
        "num_cols": num_cols,
        "primary_col": primary,
        "suggested": {"usl": _r(m + 4*s), "lsl": _r(m - 4*s), "target": _r(m)},
    })


@app.route("/api/overview")
def overview():
    token = request.args.get("token", "")
    col   = request.args.get("col", "")
    usl   = request.args.get("usl",    type=float)
    lsl   = request.args.get("lsl",    type=float)
    target= request.args.get("target", type=float)

    df = _store.get(token)
    if df is None:
        return jsonify({"error": "Session expired — re-upload file"}), 400

    vals = _vals(df, col)
    if not len(vals):
        return jsonify({"error": "No data"}), 400

    m  = _avg(vals)
    sw = _sigma_w(vals)
    ucl, lcl = m + 3*sw, m - 3*sw
    cap  = _cap(vals, usl, lsl, target)
    vios = _violations(vals, ucl, lcl, m)

    dec_v, dec_l, step = _decimate(vals)
    dec_vio = [v if (v > ucl or v < lcl) else None for v in dec_v]

    mr  = np.abs(np.diff(vals))
    mr_mean = float(np.mean(mr))
    mr_ucl  = 3.267 * mr_mean
    dec_mr, dec_mrl, _ = _decimate(mr)

    num_cols = _numeric_cols(df)
    params = []
    for c in num_cols:
        vs = _vals(df, c)
        if not len(vs):
            continue
        cm  = _avg(vs)
        cs  = _std(vs)
        cu = usl if c == col else None
        cl = lsl if c == col else None
        cc  = _cap(vs, cu, cl)
        params.append({"col": c, "mean": _r(cm), "std": _r(cs),
                        "min": _r(float(np.min(vs))), "max": _r(float(np.max(vs))),
                        "usl": cu, "lsl": cl, "cpk": cc["cpk"]})

    return jsonify({
        "col": col, "mean": _r(m), "sw": _r(sw),
        "ucl": _r(ucl), "lcl": _r(lcl), "n": len(vals),
        "range": _r(float(np.max(vals) - np.min(vals))),
        "capability": cap, "violations": vios,
        "chart":    {"vals": dec_v, "labels": dec_l, "vio": dec_vio,
                     "decimated": step > 1, "step": step,
                     "s1u": _r(m+sw), "s1l": _r(m-sw),
                     "s2u": _r(m+2*sw), "s2l": _r(m-2*sw)},
        "mr_chart": {"vals": dec_mr, "labels": dec_mrl,
                     "mean": _r(mr_mean), "ucl": _r(mr_ucl)},
        "params": params,
    })


@app.route("/api/spc")
def spc():
    token      = request.args.get("token", "")
    col        = request.args.get("col", "")
    chart_type = request.args.get("type", "ichart")
    sg_size    = request.args.get("sg", type=int, default=5)
    usl        = request.args.get("usl", type=float)
    lsl        = request.args.get("lsl", type=float)

    df = _store.get(token)
    if df is None:
        return jsonify({"error": "Session expired"}), 400

    vals = _vals(df, col)
    if not len(vals):
        return jsonify({"error": "No data"}), 400

    m  = _avg(vals)
    sw = _sigma_w(vals)
    ucl, lcl = m + 3*sw, m - 3*sw
    vios = _violations(vals, ucl, lcl, m)
    vio_pts = {v["point"] for v in vios}

    result = {"col": col, "mean": _r(m), "sw": _r(sw),
              "ucl": _r(ucl), "lcl": _r(lcl), "n": len(vals),
              "violations": vios, "chart_type": chart_type,
              "s1u": _r(m+sw), "s1l": _r(m-sw),
              "s2u": _r(m+2*sw), "s2l": _r(m-2*sw)}

    if chart_type == "ichart":
        dec_v, dec_l, step = _decimate(vals)
        dec_vio = [v if (v > ucl or v < lcl) else None for v in dec_v]
        result["chart"] = {"vals": dec_v, "labels": dec_l,
                           "vio": dec_vio, "decimated": step > 1}
        mr = np.abs(np.diff(vals))
        mrm = float(np.mean(mr))
        dec_mr, dec_mrl, _ = _decimate(mr)
        result["mr_chart"] = {"vals": dec_mr, "labels": dec_mrl,
                              "mean": _r(mrm), "ucl": _r(3.267 * mrm)}

    elif chart_type == "cusum":
        k, h = 0.5 * sw, 5 * sw
        cp = cm2 = 0.0
        cp_arr, cm_arr = [], []
        for v in vals:
            cp  = max(0.0, cp  + (v - m) - k)
            cm2 = max(0.0, cm2 - (v - m) - k)
            cp_arr.append(cp); cm_arr.append(cm2)
        dc, dl, step = _decimate(np.array(cp_arr))
        dcm, _, _ = _decimate(np.array(cm_arr))
        result["chart"] = {"cp": dc, "cm": dcm, "labels": dl,
                           "h": _r(h), "decimated": step > 1}

    elif chart_type == "ewma":
        lam = 0.2
        z = float(m)
        z_arr = [z]
        for i in range(1, len(vals)):
            z = lam * float(vals[i]) + (1 - lam) * z
            z_arr.append(z)
        L = 3
        fac = [np.sqrt(lam / (2 - lam) * (1 - (1 - lam)**(2*(i+1))))
               for i in range(len(vals))]
        ucl_e = [m + L * sw * f for f in fac]
        lcl_e = [m - L * sw * f for f in fac]
        dz, dl, step = _decimate(np.array(z_arr))
        duc, _, _ = _decimate(np.array(ucl_e))
        dlc, _, _ = _decimate(np.array(lcl_e))
        result["chart"] = {"z": dz, "ucl": duc, "lcl": dlc,
                           "labels": dl, "decimated": step > 1}

    elif chart_type == "xbar":
        groups = [vals[i:i+sg_size] for i in range(0, len(vals) - sg_size + 1, sg_size)]
        if not groups:
            return jsonify({"error": "Not enough data for subgroups"}), 400
        xbars = [float(np.mean(g)) for g in groups]
        ranges= [float(np.max(g) - np.min(g)) for g in groups]
        xbb   = float(np.mean(xbars))
        rbar  = float(np.mean(ranges))
        A2 = [0,0,1.880,1.023,0.729,0.577,0.483,0.419,0.373,0.337,0.308]
        D4 = [0,0,3.267,2.574,2.282,2.114,2.004,1.924,1.864,1.816,1.777]
        si = min(sg_size, 10)
        result["chart"] = {"xbars": xbars, "ranges": ranges,
                           "labels": [f"Sg{i+1}" for i in range(len(xbars))],
                           "xbarbar": _r(xbb), "rbar": _r(rbar),
                           "ucl_x": _r(xbb + A2[si]*rbar), "lcl_x": _r(xbb - A2[si]*rbar),
                           "ucl_r": _r(D4[si]*rbar)}

    elif chart_type == "pchart":
        ns = 100
        props = np.clip(vals / 100.0, 0, 1)
        pbar  = float(np.mean(props))
        se    = float(np.sqrt(pbar * (1-pbar) / ns))
        dp, dl, step = _decimate(props)
        result["chart"] = {"props": dp, "labels": dl,
                           "pbar": _r(pbar),
                           "ucl": _r(min(pbar+3*se, 1)),
                           "lcl": _r(max(pbar-3*se, 0)),
                           "decimated": step > 1}

    return jsonify(result)


@app.route("/api/capability")
def capability():
    token  = request.args.get("token", "")
    col    = request.args.get("col", "")
    usl    = request.args.get("usl",    type=float)
    lsl    = request.args.get("lsl",    type=float)
    target = request.args.get("target", type=float)

    df = _store.get(token)
    if df is None:
        return jsonify({"error": "Session expired"}), 400

    vals = _vals(df, col)
    cap  = _cap(vals, usl, lsl, target)

    counts, edges = np.histogram(vals, bins=20)
    bin_labels = [_r(float(edges[i])) for i in range(20)]

    return jsonify({
        "col": col, "capability": cap,
        "histogram": {"counts": counts.tolist(), "labels": bin_labels},
    })


@app.route("/api/correlation")
def correlation():
    token = request.args.get("token", "")
    y_col = request.args.get("y_col", "")
    x_col = request.args.get("x_col", "")

    df = _store.get(token)
    if df is None:
        return jsonify({"error": "Session expired"}), 400

    num_cols = _numeric_cols(df)
    y_vals = _vals(df, y_col)

    corrs = []
    for c in num_cols:
        if c == y_col:
            continue
        x_vals = _vals(df, c)
        n = min(len(x_vals), len(y_vals))
        if n < 2:
            continue
        corrs.append({"col": c, "r": _r(_pearson(x_vals[:n], y_vals[:n]))})
    corrs.sort(key=lambda d: abs(d["r"] or 0), reverse=True)

    scatter = []
    r_val = None
    if x_col and x_col != y_col:
        x_vals = _vals(df, x_col)
        n = min(len(x_vals), len(y_vals))
        r_val = _r(_pearson(x_vals[:n], y_vals[:n]))
        xs, ys = x_vals[:n], y_vals[:n]
        if n > MAX_CHART_POINTS:
            step = n // MAX_CHART_POINTS
            idx  = np.arange(0, n, step)
            xs, ys = xs[idx], ys[idx]
        scatter = [{"x": _r(float(x)), "y": _r(float(y))} for x, y in zip(xs, ys)]

    return jsonify({"y_col": y_col, "x_col": x_col,
                    "correlations": corrs, "scatter": scatter, "r": r_val})


@app.route("/api/violations")
def violations():
    token = request.args.get("token", "")
    col   = request.args.get("col", "")

    df = _store.get(token)
    if df is None:
        return jsonify({"error": "Session expired"}), 400

    vals = _vals(df, col)
    m  = _avg(vals)
    sw = _sigma_w(vals)
    ucl, lcl = m + 3*sw, m - 3*sw
    vios = _violations(vals, ucl, lcl, m)

    return jsonify({"col": col, "violations": vios,
                    "mean": _r(m), "ucl": _r(ucl), "lcl": _r(lcl)})


@app.route("/api/doe")
def doe():
    token  = request.args.get("token", "")
    y_col  = request.args.get("y_col", "")
    method = request.args.get("method", "median")
    top_n  = request.args.get("top_n", type=int, default=8)

    df = _store.get(token)
    if df is None:
        return jsonify({"error": "Session expired"}), 400

    num_cols = _numeric_cols(df)
    y_vals = _vals(df, y_col)
    effects = []

    for c in num_cols:
        if c == y_col:
            continue
        x_vals = _vals(df, c)
        n = min(len(x_vals), len(y_vals))
        if n < 4:
            continue
        xs, ys = x_vals[:n], y_vals[:n]

        if method == "median":
            med = float(np.median(xs))
            lo_m, hi_m = xs <= med, xs > med
        elif method == "quartile":
            q1, q3 = float(np.percentile(xs, 25)), float(np.percentile(xs, 75))
            lo_m, hi_m = xs <= q1, xs >= q3
        else:  # thirds
            t = n // 3
            si = np.argsort(xs)
            lo_m = np.zeros(n, bool); hi_m = np.zeros(n, bool)
            lo_m[si[:t]] = True; hi_m[si[n-t:]] = True

        if not np.any(lo_m) or not np.any(hi_m):
            continue
        lo_mean = float(np.mean(ys[lo_m]))
        hi_mean = float(np.mean(ys[hi_m]))
        effects.append({"col": c, "low": _r(lo_mean),
                        "high": _r(hi_mean), "effect": _r(hi_mean - lo_mean)})

    effects.sort(key=lambda e: abs(e["effect"] or 0), reverse=True)
    return jsonify({"y_col": y_col, "method": method,
                    "effects": effects, "top_n": top_n})


@app.route("/api/rca")
def rca():
    token     = request.args.get("token", "")
    metric    = request.args.get("metric", "")
    threshold = request.args.get("threshold", type=float, default=0.90)
    direction = request.args.get("direction", "high")
    top_n     = request.args.get("top_n", type=int, default=6)

    df = _store.get(token)
    if df is None:
        return jsonify({"error": "Session expired"}), 400

    num_cols = _numeric_cols(df)
    all_vals = _vals(df, metric)
    qval = float(np.quantile(all_vals, threshold))

    ms = pd.to_numeric(df[metric], errors="coerce")
    fail_mask   = ms >= qval if direction == "high" else ms <= qval
    fail_rows   = df[fail_mask & ms.notna()]
    normal_rows = df[~fail_mask & ms.notna()]

    input_cols = [c for c in num_cols if c != metric and
                  not any(kw in c.lower() for kw in
                          ("yield","defect","particle","thick","film","rate","uniform","refract"))]
    fcols = input_cols[:top_n]

    factor_cmp = []
    for c in fcols:
        fv = pd.to_numeric(fail_rows[c],   errors="coerce").dropna().values.astype(float)
        nv = pd.to_numeric(normal_rows[c], errors="coerce").dropna().values.astype(float)
        if not len(fv) or not len(nv):
            continue
        fm, nm = float(np.mean(fv)), float(np.mean(nv))
        dev = ((fm - nm) / nm * 100) if nm != 0 else 0
        factor_cmp.append({"col": c, "fail_mean": _r(fm),
                            "norm_mean": _r(nm), "dev_pct": _r(dev)})

    dec_v, dec_l, _ = _decimate(all_vals)
    fail_time = [v if (direction == "high" and v >= qval) or
                        (direction == "low"  and v <= qval) else None
                 for v in dec_v]

    avail = [c for c in (["Wafer_ID", "Tool_ID", "Chamber_ID"] + input_cols[:4] + [metric])
             if c in df.columns]
    preview = fail_rows[avail].head(25).fillna("").to_dict(orient="records")

    return jsonify({
        "metric": metric, "total": len(df),
        "failed": len(fail_rows),
        "fail_rate": _r(len(fail_rows) / len(df) * 100),
        "threshold_val": _r(qval),
        "factor_comparison": factor_cmp,
        "time_chart": {"vals": dec_v, "labels": dec_l, "fail_mask": fail_time},
        "fail_preview": preview, "avail_cols": avail,
    })


@app.route("/api/trend")
def trend():
    token      = request.args.get("token", "")
    col        = request.args.get("col", "")
    forecast_n = request.args.get("forecast_n", type=int, default=20)
    method     = request.args.get("method", "linear")
    target_cpk = request.args.get("target_cpk", type=float, default=1.33)
    usl        = request.args.get("usl", type=float)
    lsl        = request.args.get("lsl", type=float)

    df = _store.get(token)
    if df is None:
        return jsonify({"error": "Session expired"}), 400

    vals = _vals(df, col)
    n    = len(vals)
    m    = _avg(vals)
    sw   = _sigma_w(vals)
    ucl, lcl = m + 3*sw, m - 3*sw
    xs   = np.arange(1, n + 1, dtype=float)

    if method == "linear":
        slope, intercept = _linreg(xs, vals)
        trend_line   = slope * xs + intercept
        fxs          = np.arange(n + 1, n + forecast_n + 1, dtype=float)
        forecast_arr = slope * fxs + intercept
        residuals    = vals - trend_line
        res_se       = float(np.std(residuals, ddof=1))
        ci95         = [res_se * 1.96] * forecast_n
        r2 = 1 - float(np.sum(residuals**2)) / max(float(np.sum((vals - m)**2)), 1e-10)
        if slope != 0:
            limit_target = ucl if slope > 0 else lcl
            runs_to = abs((limit_target - float(vals[-1])) / slope)
        else:
            runs_to = None
        drift_info = {
            "slope": _r(float(slope)),
            "direction": "up" if slope > 1e-8 else ("down" if slope < -1e-8 else "stable"),
            "runs_to_limit": _r(runs_to) if runs_to and np.isfinite(runs_to) else None,
            "r2": _r(r2),
        }
    else:  # ewma
        lam = 0.3
        z = float(m)
        ewma = [z]
        for i in range(1, n):
            z = lam * float(vals[i]) + (1 - lam) * z
            ewma.append(z)
        trend_line   = np.array(ewma)
        last_z       = ewma[-1]
        forecast_arr = np.full(forecast_n, last_z)
        ci95         = [sw * (i + 1) * 0.15 for i in range(forecast_n)]
        drift_info   = {"ewma_last": _r(last_z), "mean": _r(float(m)), "sw": _r(sw)}

    dec_v, dec_l, step = _decimate(vals)
    dec_t, _, _         = _decimate(trend_line)

    cap = _cap(vals, usl, lsl)
    cpk = cap["cpk"] or 0
    req_sw = (usl - lsl) / (6 * target_cpk) if usl and lsl and target_cpk > 0 else None

    return jsonify({
        "col": col, "mean": _r(float(m)), "ucl": _r(ucl), "lcl": _r(lcl),
        "n": n, "actual": dec_v, "labels": dec_l, "trend": dec_t,
        "decimated": step > 1,
        "forecast": [_r(float(v)) for v in forecast_arr],
        "forecast_labels": list(range(n + 1, n + forecast_n + 1)),
        "ci95": [_r(float(v)) for v in ci95],
        "last_actual": _r(float(vals[-1])),
        "last_forecast": _r(float(forecast_arr[-1])),
        "drift": drift_info,
        "cpk": _r(cpk), "target_cpk": target_cpk,
        "required_sw": _r(float(req_sw)) if req_sw else None,
    })


@app.route("/api/tools")
def tools():
    token  = request.args.get("token", "")
    metric = request.args.get("metric", "")
    usl    = request.args.get("usl", type=float)
    lsl    = request.args.get("lsl", type=float)

    df = _store.get(token)
    if df is None:
        return jsonify({"error": "Session expired"}), 400

    tool_col = next((c for c in df.columns if any(kw in c.lower() for kw in ("tool","equip"))), None)
    cham_col = next((c for c in df.columns if any(kw in c.lower() for kw in ("chamber","cham"))), None)

    def _tool_stats(group_col, ids):
        result = []
        for tid in ids:
            rows = df[df[group_col] == tid]
            vs   = pd.to_numeric(rows[metric], errors="coerce").dropna().values.astype(float)
            if not len(vs):
                continue
            m_v  = float(np.mean(vs))
            s_v  = float(np.std(vs, ddof=1)) if len(vs) > 1 else 0
            sw_v = _sigma_w(vs)
            vios = _violations(vs, m_v + 3*sw_v, m_v - 3*sw_v, m_v) if sw_v > 0 else []
            cc   = _cap(vs, usl, lsl)
            result.append({"id": str(tid), "mean": _r(m_v), "std": _r(s_v),
                           "n": len(vs), "violations": len(vios), "cpk": cc["cpk"]})
        return result

    tools_data = _tool_stats(tool_col, df[tool_col].dropna().unique().tolist()) if tool_col else []
    chams_data = _tool_stats(cham_col, df[cham_col].dropna().unique().tolist()) if cham_col else []

    return jsonify({"tool_col": tool_col, "cham_col": cham_col,
                    "tools": tools_data, "chambers": chams_data})


if __name__ == "__main__":
    os.makedirs("templates", exist_ok=True)
    print("🚀  Thin Film SPC Analyzer — Python backend")
    print("    http://127.0.0.1:5000")
    app.run(debug=False, host="0.0.0.0", port=5000)
