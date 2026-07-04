"""
cycle_solver.py — Steady-State Vapor Compression Cycle Solver
==============================================================

Predicts the steady-state operating point of a refrigeration system given
component specifications (compressor displacement, condenser UA, evaporator UA,
TXV Cv) and external conditions (water inlet temp, GPM, air temperature).

By comparing predicted vs actual sensor readings, the diagnostics engine
(PV-1 scenario) can pinpoint root causes with much higher precision than
threshold rules alone.

SOLVER SUMMARY
--------------
Unknowns : T_evap [°F], T_cond [°F]  (saturation temperatures)
Equations:
  1.  Evaporator energy balance:  m_dot*(h1-h4) = UA_evap*(T_air - T_evap)
  2.  Mass-flow balance:          m_dot_comp    = m_dot_txv

All SI internally.  Public API uses imperial units (°F, PSIG, BTU/hr, lb/hr).

USAGE
-----
    from cycle_solver import solve_cycle, extract_specs_from_model, extract_conditions_from_df

    specs      = extract_specs_from_model(diagram_model)
    conditions = extract_conditions_from_df(processed_df)
    solution   = solve_cycle(specs, conditions)

    if solution.converged:
        print(f"T_evap={solution.T_evap_F:.1f}°F  T_cond={solution.T_cond_F:.1f}°F")
        print(f"COP={solution.COP:.2f}  Q_evap={solution.Q_evap_btu_hr/1000:.1f} kBTU/hr")
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

try:
    import CoolProp.CoolProp as CP
    _COOLPROP_AVAILABLE = True
except Exception:
    CP = None  # type: ignore
    _COOLPROP_AVAILABLE = False

try:
    from scipy.optimize import fsolve
    _SCIPY_AVAILABLE = True
except Exception:
    fsolve = None  # type: ignore
    _SCIPY_AVAILABLE = False

logger = logging.getLogger(__name__)

# ─── CONSTANTS ────────────────────────────────────────────────────────────────

# Water heat capacity × density product  (BTU / (hr·GPM·°F))
# Q_water = 500.4 * GPM * ΔT_water  (industry standard)
_KW_PER_GPM_DELTA_F = 500.4          # BTU/hr per GPM per °F

# Cp of liquid water ≈ 4187 J/(kg·K), ρ_water ≈ 997 kg/m3
# C_water = GPM * (3.785e-3 m3/min / 60 s/min) * ρ * Cp
# = GPM * 6.309e-5 * 997 * 4187 = GPM * 263.5  [W/°C per GPM]
_C_WATER_PER_GPM = 263.5             # W/K per GPM  (used for condenser NTU model)

# TXV flow constant:
# m_dot_txv [kg/s] = Cv * C_TXV * sqrt(2 * ΔP [Pa] * ρ_liq [kg/m3])
# Calibrated so Cv=0.5 gives ~0.006 kg/s at ΔP=500 kPa, ρ=480 kg/m3
_C_TXV = 5.5e-7                      # [—]  (embedded unit conversion)

# Volumetric efficiency model:  η_vol = max(η_vol_max - 0.05*(PR-1), η_vol_min)
_VOL_EFF_MAX  = 0.95
_VOL_EFF_MIN  = 0.40
_VOL_EFF_SLOPE = 0.05

# ─── DATA CLASSES ─────────────────────────────────────────────────────────────

@dataclass
class ComponentSpecs:
    """
    Solver-relevant component specifications extracted from the diagram model.

    All values come from the component schemas:
      Compressor.displacement_cm3   → cm3/rev
      Compressor.speed_rpm          → RPM
      Compressor.vol_eff            → 0–1  (η_vol, if pre-computed; else derived from PR)
      Compressor.isentropic_eff     → 0–1  (η_is)
      Condenser.ua_condenser        → W/K
      Condenser.condenser_type      → 'Water Cooled' | 'Air Cooled'
      Evaporator.ua_evaporator      → W/K
      TXV.cv_txv                    → dimensionless flow coefficient
      TXV.superheat_setting         → °F
    """
    # Compressor
    displacement_cm3: float = 10.5
    speed_rpm: float        = 3500.0
    vol_eff_nominal: float  = 0.85    # used only if use_nominal_vol_eff=True
    isentropic_eff: float   = 0.72
    use_nominal_vol_eff: bool = False  # True → use vol_eff_nominal; False → derive from PR

    # Condenser
    ua_condenser: float        = 800.0      # W/K
    condenser_type: str        = 'Water Cooled'

    # Evaporator
    ua_evaporator: float = 600.0     # W/K

    # TXV
    cv_txv: float         = 0.5
    sh_setpoint_F: float  = 12.0     # TXV superheat setpoint [°F]

    # Refrigerant
    refrigerant: str = 'R290'


@dataclass
class ExternalConditions:
    """
    External boundary conditions for the cycle solver.

    Drawn from sensor data (latest averages) or from rated_inputs.
    """
    # Water-cooled condenser inputs
    T_water_in_F: float = 65.0     # condenser water inlet temperature [°F]
    water_gpm: float    = 3.0      # condenser water flow rate [GPM]

    # Evaporator air-side input
    T_air_F: float = 35.0          # air temperature around evaporator / case temp [°F]


@dataclass
class CycleSolution:
    """
    Predicted steady-state operating point from the cycle solver.
    All temperatures in °F, pressures in PSIG, flow in lb/hr, energy in BTU/hr.
    """
    converged: bool   = False
    iterations: int   = 0
    error_msg: str    = ''

    # Saturation conditions
    T_evap_F: float   = 0.0    # evap saturation temperature [°F]
    T_cond_F: float   = 0.0    # cond saturation temperature [°F]
    P_evap_psig: float = 0.0
    P_cond_psig: float = 0.0
    PR: float          = 0.0   # pressure ratio (absolute)

    # State points (enthalpy kJ/kg)
    h1: float = 0.0    # compressor inlet (suction gas with SH)
    h2: float = 0.0    # compressor outlet (discharge gas)
    h3: float = 0.0    # condenser outlet (subcooled liquid)
    h4: float = 0.0    # TXV outlet = h3 (two-phase mixture)

    # Temperatures at key points [°F]
    T_suction_F: float  = 0.0   # T1 = T_evap + SH
    T_disch_F: float    = 0.0   # T2 (discharge temp)
    T_liquid_F: float   = 0.0   # T3 (condenser outlet)
    T_water_out_F: float = 0.0  # predicted water outlet temp

    # Superheat / subcooling [°F]
    SH_F: float = 0.0    # at compressor inlet
    SC_F: float = 0.0    # at condenser outlet

    # Mass flow
    m_dot_lbhr: float = 0.0    # lb/hr
    eta_vol: float    = 0.0    # actual volumetric efficiency used

    # Performance
    Q_evap_btu_hr: float = 0.0
    Q_cond_btu_hr: float = 0.0
    W_comp_kW: float     = 0.0
    COP: float           = 0.0


# ─── UNIT HELPERS ─────────────────────────────────────────────────────────────

def _f_to_k(T_F: float) -> float:
    return (T_F + 459.67) * 5.0 / 9.0


def _k_to_f(T_K: float) -> float:
    return T_K * 9.0 / 5.0 - 459.67


def _pa_to_psig(P_pa: float) -> float:
    return P_pa / 6894.76 - 14.696


def _psig_to_pa(P_psig: float) -> float:
    return (P_psig + 14.696) * 6894.76


def _kjs_to_btuhr(kW: float) -> float:
    """kW → BTU/hr"""
    return kW * 3412.14


def _jkg_to_btulb(j_per_kg: float) -> float:
    return j_per_kg * 0.0004299


# ─── HEAT EXCHANGER HELPERS ───────────────────────────────────────────────────

def lmtd_counterflow(T_hot_in: float, T_hot_out: float,
                     T_cold_in: float, T_cold_out: float) -> float:
    """
    Log Mean Temperature Difference for a counter-flow heat exchanger [K or °F].

    T_hot_in  > T_hot_out  (hot fluid cools down)
    T_cold_out > T_cold_in  (cold fluid heats up)

    Returns 0 if degenerate (all temperatures equal).
    """
    dT1 = T_hot_in  - T_cold_out   # hot-end temperature difference
    dT2 = T_hot_out - T_cold_in    # cold-end temperature difference

    if abs(dT1) < 1e-6 and abs(dT2) < 1e-6:
        return 0.0
    if abs(dT1 - dT2) < 1e-6:
        return dT1  # avoid ln(1) = 0 division
    if dT1 <= 0 or dT2 <= 0:
        # Temperature cross — use arithmetic mean as fallback
        return (abs(dT1) + abs(dT2)) / 2.0
    return (dT1 - dT2) / math.log(dT1 / dT2)


def _condenser_q_ntu(UA: float, water_gpm: float,
                     T_cond_K: float, T_water_in_K: float) -> tuple[float, float]:
    """
    Predict condenser heat rejection using the NTU-effectiveness method.

    For a condenser operating at constant T_cond (phase change side):
        NTU       = UA / C_min    where C_min = C_water = GPM × 263.5  [W/K]
        epsilon   = 1 - exp(-NTU)
        Q_cond    = epsilon × C_water × (T_cond - T_water_in)
        T_water_out = T_water_in + Q_cond / C_water

    Parameters
    ----------
    UA         : W/K
    water_gpm  : GPM
    T_cond_K   : condensing temperature [K]
    T_water_in_K : water inlet temperature [K]

    Returns
    -------
    (Q_cond_W, T_water_out_K)
    """
    C_water = water_gpm * _C_WATER_PER_GPM      # W/K
    if C_water < 1.0:
        C_water = 1.0  # prevent divide-by-zero

    NTU       = UA / C_water
    epsilon   = 1.0 - math.exp(-NTU)
    Q_cond    = epsilon * C_water * (T_cond_K - T_water_in_K)
    T_water_out_K = T_water_in_K + Q_cond / C_water

    return Q_cond, T_water_out_K


def _vol_eff_from_pr(PR: float, nominal: float | None = None) -> float:
    """
    Estimate volumetric efficiency from pressure ratio.

    Uses a simple linear model: η_vol = η_max - 0.05*(PR - 1)
    Clamped to [η_vol_min, η_vol_max].
    """
    if nominal is not None:
        return float(nominal)
    eta = _VOL_EFF_MAX - _VOL_EFF_SLOPE * (PR - 1.0)
    return max(_VOL_EFF_MIN, min(_VOL_EFF_MAX, eta))


# ─── CORE CYCLE SOLVER ────────────────────────────────────────────────────────

def _cycle_residuals(x: np.ndarray, specs: ComponentSpecs,
                     conditions: ExternalConditions) -> np.ndarray:
    """
    Residual function for the steady-state cycle solver.

    Parameters
    ----------
    x[0] : T_evap [°F]  (saturation temperature in evaporator)
    x[1] : T_cond [°F]  (saturation temperature in condenser)

    Returns
    -------
    residuals [res1, res2] — both should be zero at the solution.

    Equations
    ---------
    res1 = Q_evap_ref  - Q_evap_air     [evaporator energy balance]
    res2 = m_dot_comp  - m_dot_txv      [TXV mass-flow balance]
    """
    if CP is None:
        return np.array([1e6, 1e6])

    T_evap_F, T_cond_F = float(x[0]), float(x[1])
    ref = specs.refrigerant

    try:
        # ── Convert to SI ────────────────────────────────────────────────────
        T_evap_K = _f_to_k(T_evap_F)
        T_cond_K = _f_to_k(T_cond_F)

        # ── Saturation pressures ─────────────────────────────────────────────
        P_evap = CP.PropsSI('P', 'T', T_evap_K, 'Q', 0.5, ref)
        P_cond = CP.PropsSI('P', 'T', T_cond_K, 'Q', 0.5, ref)

        if P_evap <= 0 or P_cond <= 0 or P_cond <= P_evap:
            return np.array([1e6, 1e6])

        PR = P_cond / P_evap

        # ── State 1: compressor inlet (superheated gas) ──────────────────────
        T1_F = T_evap_F + specs.sh_setpoint_F
        T1_K = _f_to_k(T1_F)
        h1   = CP.PropsSI('H', 'T', T1_K, 'P', P_evap, ref)   # J/kg
        s1   = CP.PropsSI('S', 'T', T1_K, 'P', P_evap, ref)   # J/(kg·K)
        rho1 = CP.PropsSI('D', 'T', T1_K, 'P', P_evap, ref)   # kg/m3

        # ── Compressor model ─────────────────────────────────────────────────
        eta_vol   = _vol_eff_from_pr(PR,
                        specs.vol_eff_nominal if specs.use_nominal_vol_eff else None)
        V_disp_m3 = specs.displacement_cm3 * 1e-6   # cm3 → m3
        rpm_s     = specs.speed_rpm / 60.0           # RPM → rev/s

        m_dot_comp = V_disp_m3 * rpm_s * rho1 * eta_vol   # kg/s

        if m_dot_comp <= 0:
            return np.array([1e6, 1e6])

        # ── State 2: compressor outlet (actual discharge) ────────────────────
        h2s  = CP.PropsSI('H', 'S', s1, 'P', P_cond, ref)   # isentropic h [J/kg]
        h2   = h1 + (h2s - h1) / specs.isentropic_eff        # actual discharge h

        # ── Condenser (NTU-effectiveness) ────────────────────────────────────
        T_water_in_K = _f_to_k(conditions.T_water_in_F)
        Q_cond, _    = _condenser_q_ntu(
            specs.ua_condenser, conditions.water_gpm,
            T_cond_K, T_water_in_K
        )

        # Condenser outlet enthalpy
        h3 = h2 - Q_cond / m_dot_comp    # J/kg (subcooled liquid)

        # ── TXV: isenthalpic expansion ───────────────────────────────────────
        h4 = h3   # isenthalpic

        # ── Evaporator energy balance ─────────────────────────────────────────
        Q_evap_ref = m_dot_comp * (h1 - h4)   # W
        T_air_K    = _f_to_k(conditions.T_air_F)
        Q_evap_air = specs.ua_evaporator * (T_air_K - T_evap_K)   # W

        res1 = Q_evap_ref - Q_evap_air

        # ── TXV mass-flow balance ─────────────────────────────────────────────
        rho_liq  = CP.PropsSI('D', 'T', T_cond_K, 'Q', 0.0, ref)   # liquid density
        dP       = max(P_cond - P_evap, 1.0)                         # Pa

        m_dot_txv = (specs.cv_txv * _C_TXV
                     * math.sqrt(2.0 * dP * rho_liq))   # kg/s

        res2 = m_dot_comp - m_dot_txv

        # Scale residuals to similar magnitudes (~W and ~kg/s×1000)
        return np.array([res1 / 1000.0, res2 * 1000.0])

    except Exception as exc:
        logger.debug('[CYCLE_SOLVER] Residual error at (%.1f, %.1f): %s',
                     T_evap_F, T_cond_F, exc)
        return np.array([1e6, 1e6])


def solve_cycle(specs: ComponentSpecs,
                conditions: ExternalConditions,
                max_attempts: int = 4) -> CycleSolution:
    """
    Find the steady-state operating point of the refrigeration cycle.

    Uses scipy.optimize.fsolve (Newton-Krylov / Powell hybrid).

    Parameters
    ----------
    specs      : ComponentSpecs  — component sizing + refrigerant
    conditions : ExternalConditions — water inlet temp, GPM, air temp
    max_attempts : int — number of initial-guess strategies to try before giving up

    Returns
    -------
    CycleSolution with converged=True on success.
    """
    sol = CycleSolution()

    if not _COOLPROP_AVAILABLE:
        sol.error_msg = 'CoolProp not available'
        return sol
    if not _SCIPY_AVAILABLE:
        sol.error_msg = 'scipy not available'
        return sol

    # ── Initial guesses ───────────────────────────────────────────────────────
    # Multiple starting points to improve robustness
    T_air_F   = conditions.T_air_F
    T_water_F = conditions.T_water_in_F

    initial_guesses = [
        [T_air_F - 10.0,  T_water_F + 15.0],  # typical 10°F TD, 15°F approach
        [T_air_F - 15.0,  T_water_F + 20.0],  # slightly more conservative
        [T_air_F -  5.0,  T_water_F + 10.0],  # warmer evap / cooler cond
        [T_air_F - 20.0,  T_water_F + 25.0],  # more aggressive guess
    ]

    best_x    = None
    best_resid = 1e9

    for i, x0 in enumerate(initial_guesses[:max_attempts]):
        try:
            x_sol, info, ier, msg = fsolve(
                _cycle_residuals, x0,
                args=(specs, conditions),
                full_output=True,
                xtol=1e-4,     # 0.0001°F temperature tolerance
                maxfev=500,
            )
            resid = float(np.max(np.abs(info['fvec'])))
            if resid < best_resid:
                best_resid = resid
                best_x     = x_sol
            if ier == 1 and resid < 1.0:   # converged
                break
        except Exception as exc:
            logger.debug('[CYCLE_SOLVER] fsolve attempt %d failed: %s', i, exc)
            continue

    if best_x is None:
        sol.error_msg = 'Solver failed to run (all attempts raised exceptions)'
        return sol

    # ── Accept or reject solution ────────────────────────────────────────────
    T_evap_F, T_cond_F = float(best_x[0]), float(best_x[1])

    # Sanity checks
    if T_evap_F >= T_cond_F:
        sol.error_msg = f'Non-physical solution: T_evap ({T_evap_F:.1f}°F) >= T_cond ({T_cond_F:.1f}°F)'
        return sol
    if T_evap_F < -60.0 or T_evap_F > 60.0:
        sol.error_msg = f'T_evap out of range: {T_evap_F:.1f}°F'
        return sol
    if T_cond_F < 50.0 or T_cond_F > 160.0:
        sol.error_msg = f'T_cond out of range: {T_cond_F:.1f}°F'
        return sol
    if best_resid > 5.0:
        sol.error_msg = (f'Residuals too large ({best_resid:.2f}) — '
                         'check component specs and external conditions')
        return sol

    # ── Build full solution state ─────────────────────────────────────────────
    return _build_solution(T_evap_F, T_cond_F, specs, conditions)


def _build_solution(T_evap_F: float, T_cond_F: float,
                    specs: ComponentSpecs,
                    conditions: ExternalConditions) -> CycleSolution:
    """
    Given converged (T_evap_F, T_cond_F), compute all output quantities
    and return a fully populated CycleSolution.
    """
    sol = CycleSolution()
    ref = specs.refrigerant

    try:
        T_evap_K = _f_to_k(T_evap_F)
        T_cond_K = _f_to_k(T_cond_F)

        P_evap = CP.PropsSI('P', 'T', T_evap_K, 'Q', 0.5, ref)
        P_cond = CP.PropsSI('P', 'T', T_cond_K, 'Q', 0.5, ref)
        PR     = P_cond / P_evap

        # State 1 — compressor inlet
        T1_F = T_evap_F + specs.sh_setpoint_F
        T1_K = _f_to_k(T1_F)
        h1   = CP.PropsSI('H', 'T', T1_K, 'P', P_evap, ref)
        s1   = CP.PropsSI('S', 'T', T1_K, 'P', P_evap, ref)
        rho1 = CP.PropsSI('D', 'T', T1_K, 'P', P_evap, ref)

        # Compressor
        eta_vol   = _vol_eff_from_pr(PR,
                        specs.vol_eff_nominal if specs.use_nominal_vol_eff else None)
        V_disp_m3 = specs.displacement_cm3 * 1e-6
        rpm_s     = specs.speed_rpm / 60.0
        m_dot     = V_disp_m3 * rpm_s * rho1 * eta_vol   # kg/s

        # State 2 — compressor outlet
        h2s   = CP.PropsSI('H', 'S', s1, 'P', P_cond, ref)
        h2    = h1 + (h2s - h1) / specs.isentropic_eff
        T2_K  = CP.PropsSI('T', 'H', h2, 'P', P_cond, ref)

        # Condenser (NTU)
        T_water_in_K  = _f_to_k(conditions.T_water_in_F)
        Q_cond, T_water_out_K = _condenser_q_ntu(
            specs.ua_condenser, conditions.water_gpm,
            T_cond_K, T_water_in_K
        )

        # State 3 — condenser outlet
        h3   = h2 - Q_cond / m_dot
        T3_K = CP.PropsSI('T', 'H', h3, 'P', P_cond, ref)

        # Subcooling
        hf_cond = CP.PropsSI('H', 'T', T_cond_K, 'Q', 0.0, ref)
        # SC = T_sat.cond - T_liquid  (both in °F)
        SC_F = _k_to_f(T_cond_K) - _k_to_f(T3_K)

        # State 4 — TXV outlet
        h4 = h3

        # Performance
        Q_evap_W  = m_dot * (h1 - h4)                   # W
        W_comp_W  = m_dot * (h2 - h1)                   # W (actual shaft power)
        COP       = Q_evap_W / W_comp_W if W_comp_W > 0 else 0.0

        # ── Populate solution ─────────────────────────────────────────────────
        sol.converged      = True
        sol.T_evap_F       = T_evap_F
        sol.T_cond_F       = T_cond_F
        sol.P_evap_psig    = _pa_to_psig(P_evap)
        sol.P_cond_psig    = _pa_to_psig(P_cond)
        sol.PR             = PR

        sol.h1             = h1 / 1000.0     # kJ/kg
        sol.h2             = h2 / 1000.0
        sol.h3             = h3 / 1000.0
        sol.h4             = h4 / 1000.0

        sol.T_suction_F    = T1_F
        sol.T_disch_F      = _k_to_f(T2_K)
        sol.T_liquid_F     = _k_to_f(T3_K)
        sol.T_water_out_F  = _k_to_f(T_water_out_K)

        sol.SH_F           = specs.sh_setpoint_F   # TXV setpoint
        sol.SC_F           = SC_F

        sol.m_dot_lbhr     = m_dot * 7936.64     # kg/s → lb/hr
        sol.eta_vol        = eta_vol

        sol.Q_evap_btu_hr  = Q_evap_W * 3.41214  # W → BTU/hr
        sol.Q_cond_btu_hr  = Q_cond * 3.41214
        sol.W_comp_kW      = W_comp_W / 1000.0
        sol.COP            = COP

    except Exception as exc:
        sol.converged  = False
        sol.error_msg  = f'Solution build error: {exc}'

    return sol


# ─── SPEC / CONDITION EXTRACTORS ──────────────────────────────────────────────

def extract_specs_from_model(diagram_model: dict) -> ComponentSpecs:
    """
    Pull component specifications from the diagram model's component properties.

    Scans all components for:
      - First Compressor  → displacement, speed, vol_eff, isentropic_eff
      - First Condenser   → ua_condenser, condenser_type
      - First Evaporator  → ua_evaporator
      - First TXV         → cv_txv, superheat_setting

    Returns ComponentSpecs with defaults for any missing values.
    """
    specs = ComponentSpecs()

    comps = (diagram_model or {}).get('components', {})
    if not comps:
        return specs

    _found_comp = _found_cond = _found_evap = _found_txv = False

    for comp in comps.values():
        ctype = (comp or {}).get('type', '')
        props = (comp or {}).get('properties', {}) or {}

        if ctype == 'Compressor' and not _found_comp:
            specs.displacement_cm3  = float(props.get('displacement_cm3', specs.displacement_cm3))
            specs.speed_rpm         = float(props.get('speed_rpm',         specs.speed_rpm))
            specs.vol_eff_nominal   = float(props.get('vol_eff',           specs.vol_eff_nominal))
            specs.isentropic_eff    = float(props.get('isentropic_eff',    specs.isentropic_eff))
            _found_comp = True

        elif ctype == 'Condenser' and not _found_cond:
            specs.ua_condenser   = float(props.get('ua_condenser',  specs.ua_condenser))
            specs.condenser_type = str  (props.get('condenser_type', specs.condenser_type))
            _found_cond = True

        elif ctype == 'Evaporator' and not _found_evap:
            specs.ua_evaporator = float(props.get('ua_evaporator', specs.ua_evaporator))
            _found_evap = True

        elif ctype == 'TXV' and not _found_txv:
            specs.cv_txv        = float(props.get('cv_txv',           specs.cv_txv))
            specs.sh_setpoint_F = float(props.get('superheat_setting', specs.sh_setpoint_F))
            _found_txv = True

    return specs


def extract_conditions_from_df(processed_df, rated_inputs: dict = None) -> ExternalConditions:
    """
    Pull external boundary conditions from the most recent rows of processed_df.

    Looks for columns:
      - T_waterin / T_waterout  → condenser water temperatures
      - T_air_*                 → evaporator air temperature
      - Rated inputs for GPM (water_gpm)

    Falls back to defaults from ExternalConditions if columns are missing.
    """
    cond = ExternalConditions()

    if rated_inputs:
        gpm = rated_inputs.get('gpm_water')
        if gpm and gpm > 0:
            cond.water_gpm = float(gpm)

    if processed_df is None or processed_df.empty:
        return cond

    # Use the last 5 rows (most recent steady-state data)
    recent = processed_df.tail(5)

    def _mean_col(col: str) -> Optional[float]:
        if col in recent.columns:
            v = recent[col].dropna()
            return float(v.mean()) if len(v) > 0 else None
        return None

    # Water inlet temperature
    t_win = _mean_col('T_waterin')
    if t_win is None:
        # Try cassette-style columns (any -lh / -rh suffix)
        for c in processed_df.columns:
            if c.startswith('T_waterin'):
                v = _mean_col(c)
                if v is not None:
                    t_win = v
                    break
    if t_win is not None:
        cond.T_water_in_F = t_win

    # Air temperature around evaporator
    # Prefer T_sat.comp.in as a proxy (evap saturation = closest to air temp)
    # If real air sensors exist they'll override this
    t_air_candidates = ['T_air', 'T_ambient', 'T_case', 'T_air_avg']
    for col in t_air_candidates:
        v = _mean_col(col)
        if v is not None:
            cond.T_air_F = v
            break
    else:
        # Use T_sat.comp.in + 10°F as a reasonable approximation of air temp
        t_sat = _mean_col('T_sat.comp.in')
        if t_sat is not None:
            cond.T_air_F = t_sat + 10.0

    return cond


# ─── DEVIATION ANALYSIS ───────────────────────────────────────────────────────

@dataclass
class ParameterDeviation:
    """One predicted-vs-actual comparison."""
    name: str
    predicted: float
    actual: float
    delta: float
    unit: str
    tolerance: float
    severity: str    # 'OK' | 'WATCH' | 'WARNING' | 'CRITICAL'
    flag: str        # '' | '✓' | '⚠' | '⚠⚠' | '⚠⚠⚠'


def compute_deviations(solution: CycleSolution,
                       actual: dict,
                       thresholds: dict) -> list[ParameterDeviation]:
    """
    Compare cycle solver predictions to actual sensor averages.

    Parameters
    ----------
    solution   : CycleSolution from solve_cycle()
    actual     : dict of actual sensor averages, keys:
                   P_suction, P_disch, S.H_total, S.C, T_3a (discharge temp),
                   qc (BTU/hr), m_dot (lb/hr)
    thresholds : dict with tolerance keys (falls back to defaults)

    Returns
    -------
    List of ParameterDeviation, one per compared parameter.
    """
    _tol = lambda key, default: thresholds.get(key, default)

    deviations: list[ParameterDeviation] = []

    def _dev(name: str, pred: float, act: Optional[float],
             unit: str, tol: float) -> Optional[ParameterDeviation]:
        if act is None or math.isnan(act):
            return None
        delta = act - pred
        abs_d = abs(delta)
        if abs_d <= tol:
            sev, flag = 'OK', '✓'
        elif abs_d <= 2 * tol:
            sev, flag = 'WATCH', '⚠'
        elif abs_d <= 3 * tol:
            sev, flag = 'WARNING', '⚠⚠'
        else:
            sev, flag = 'CRITICAL', '⚠⚠⚠'
        return ParameterDeviation(name, pred, act, delta, unit, tol, sev, flag)

    # Suction pressure
    d = _dev('P_suction', solution.P_evap_psig, actual.get('P_suction'),
             'PSIG', _tol('P_suction_tol_psi', 5.0))
    if d: deviations.append(d)

    # Discharge pressure
    d = _dev('P_disch', solution.P_cond_psig, actual.get('P_disch'),
             'PSIG', _tol('P_disch_tol_psi', 8.0))
    if d: deviations.append(d)

    # Total superheat
    d = _dev('SH (total)', solution.SH_F, actual.get('S.H_total'),
             '°F', _tol('SH_tol_F', 5.0))
    if d: deviations.append(d)

    # Subcooling
    d = _dev('SC', solution.SC_F, actual.get('S.C'),
             '°F', _tol('SC_tol_F', 3.0))
    if d: deviations.append(d)

    # Discharge temperature
    d = _dev('T_disch', solution.T_disch_F, actual.get('T_3a'),
             '°F', _tol('T_disch_tol_F', 15.0))
    if d: deviations.append(d)

    # Cooling capacity
    qc_actual = actual.get('qc')
    if qc_actual and solution.Q_evap_btu_hr > 0:
        qc_pct_tol = _tol('capacity_tol_pct', 15.0)
        pct_dev    = 100.0 * (qc_actual - solution.Q_evap_btu_hr) / solution.Q_evap_btu_hr
        abs_pct    = abs(pct_dev)
        if abs_pct <= qc_pct_tol:
            sev, flag = 'OK', '✓'
        elif abs_pct <= 2 * qc_pct_tol:
            sev, flag = 'WATCH', '⚠'
        elif abs_pct <= 3 * qc_pct_tol:
            sev, flag = 'WARNING', '⚠⚠'
        else:
            sev, flag = 'CRITICAL', '⚠⚠⚠'
        deviations.append(ParameterDeviation(
            'Q_evap', solution.Q_evap_btu_hr / 1000.0, qc_actual / 1000.0,
            pct_dev, 'kBTU/hr (%)', qc_pct_tol, sev, flag
        ))

    return deviations


def infer_root_cause(deviations: list[ParameterDeviation]) -> tuple[str, str]:
    """
    Pattern-match deviations to the most likely root cause.

    Returns
    -------
    (root_cause_label, recommendation_text)
    """
    # Build a quick-lookup dict
    dev_map  = {d.name: d for d in deviations}
    sev_map  = {d.name: d.severity for d in deviations}
    delta_map = {d.name: d.delta for d in deviations}

    def _bad(name: str) -> bool:
        return sev_map.get(name, 'OK') in ('WARNING', 'CRITICAL')

    def _sign(name: str) -> int:
        return 1 if delta_map.get(name, 0) > 0 else -1

    # ── Pattern matching ──────────────────────────────────────────────────────

    # 1. Undercharge / TXV restriction
    #    SH ↑ (actual > predicted), SC ↓ (actual < predicted), Q ↓
    if (_bad('SH (total)') and _sign('SH (total)') > 0
            and _bad('SC') and _sign('SC') < 0):
        if _bad('P_suction') and _sign('P_suction') < 0:
            return (
                'Undercharge or refrigerant leak',
                'POSSIBLE CAUSES:\n'
                '  1. Refrigerant undercharge — check charge level, leak check system\n'
                '  2. TXV restriction — inspect TXV screen/bulb, verify superheat setpoint\n'
                '  3. Filter/dryer restriction — check pressure drop across filter dryer\n'
                '  4. Suction-side restriction — check for kinked lines or blockage\n'
                'ACTION: Compare with RF-1 (Leak Trend) and DI-2 (Filter Dryer) findings.'
            )
        else:
            return (
                'TXV starved or restricted',
                'POSSIBLE CAUSES:\n'
                '  1. TXV partially closed or internally blocked\n'
                '  2. TXV bulb mispositioned or lost contact with suction line\n'
                '  3. Liquid line restriction (filter/dryer, solenoid valve)\n'
                '  4. Low subcooling at TXV inlet — flash gas in liquid line\n'
                'ACTION: Check TX-1 finding, inspect TXV and liquid line components.'
            )

    # 2. Overcharge / TXV stuck open
    #    SH ↓ (actual < predicted, near zero), SC normal
    if _bad('SH (total)') and _sign('SH (total)') < 0:
        return (
            'TXV overfeeding or oversized',
            'POSSIBLE CAUSES:\n'
            '  1. TXV stuck open or set too low\n'
            '  2. TXV oversized for current operating conditions\n'
            '  3. Refrigerant overcharge\n'
            '  4. TXV bulb not sensing correctly (bulb displacement, loss of charge)\n'
            'ACTION: Check TX-2 finding. Risk of liquid slugging — inspect compressor.'
        )

    # 3. Condenser fouling / reduced UA
    #    P_cond ↑, SC normal, T_disch ↑
    if (_bad('P_disch') and _sign('P_disch') > 0
            and _bad('T_disch') and _sign('T_disch') > 0):
        return (
            'Condenser underperforming (reduced effective UA)',
            'POSSIBLE CAUSES:\n'
            '  1. Condenser fouling — check water-side scale or air-side fin blockage\n'
            '  2. Water flow lower than expected — verify GPM against spec\n'
            '  3. Water inlet temperature higher than assumed in solver\n'
            '  4. Air in water circuit (if water-cooled) — check for bubble traps\n'
            'ACTION: Verify actual water GPM. Check CD-1 and CD-2 findings.'
        )

    # 4. Evaporator underperforming
    #    P_suction ↓, SH ↑, Q ↓
    if (_bad('P_suction') and _sign('P_suction') < 0
            and _bad('Q_evap') and _sign('Q_evap') < 0):
        return (
            'Evaporator underperforming (reduced effective UA or airflow)',
            'POSSIBLE CAUSES:\n'
            '  1. Evaporator icing — product or coil temperature below 32°F\n'
            '  2. Fan failure or reduced airflow across evaporator\n'
            '  3. Evaporator fouled / blocked by debris\n'
            '  4. Air temperature lower than expected (check T_air input to solver)\n'
            'ACTION: Check EV-1, EV-3 findings. Verify evaporator fan operation.'
        )

    # 5. Compressor valve damage / reduced isentropic efficiency
    #    T_disch ↑↑, P_suction ↑ (slightly), P_disch ↓ slightly, Q ↓
    if (_bad('T_disch') and _sign('T_disch') > 0
            and not _bad('P_disch') and not _bad('SH (total)')):
        return (
            'Compressor valve wear or reduced isentropic efficiency',
            'POSSIBLE CAUSES:\n'
            '  1. Compressor discharge valve leakage (hot re-expansion)\n'
            '  2. Compressor suction valve wear (reduced volumetric efficiency)\n'
            '  3. Refrigerant-side oil contamination reducing heat transfer\n'
            '  4. Actual isentropic efficiency below spec (update isentropic_eff in specs)\n'
            'ACTION: Check CP-2, CP-5, CP-6 findings. Consider compressor replacement.'
        )

    # 6. System matches prediction
    all_ok = all(d.severity == 'OK' for d in deviations)
    if all_ok:
        return (
            'System operating as designed',
            'All measured parameters are within tolerance of the cycle solver prediction.\n'
            'The system is performing as expected given the component specifications.'
        )

    # 7. Mixed / unknown pattern
    warnings = [d.name for d in deviations if d.severity not in ('OK',)]
    return (
        'Multiple deviations detected — review individual parameters',
        f'PARAMETERS OUTSIDE TOLERANCE: {", ".join(warnings)}\n\n'
        'POSSIBLE CAUSES:\n'
        '  1. Component specifications may not match actual installed components\n'
        '     — update UA_condenser, UA_evaporator, Cv_TXV in component properties\n'
        '  2. External conditions differ from solver assumptions\n'
        '     — verify water GPM, water inlet temp, and air temp inputs\n'
        '  3. Multiple simultaneous faults\n'
        '  4. Data quality issue — check sensor calibration\n'
        'ACTION: Review all individual diagnostic findings.'
    )


# ─── STANDALONE TEST ───────────────────────────────────────────────────────────

if __name__ == '__main__':
    """Quick smoke-test at nominal R290 conditions."""
    logging.basicConfig(level=logging.DEBUG)

    test_specs = ComponentSpecs(
        displacement_cm3 = 10.5,
        speed_rpm        = 3500.0,
        isentropic_eff   = 0.72,
        ua_condenser     = 800.0,
        ua_evaporator    = 600.0,
        cv_txv           = 0.5,
        sh_setpoint_F    = 12.0,
        refrigerant      = 'R290',
    )
    test_cond = ExternalConditions(
        T_water_in_F = 65.0,
        water_gpm    = 3.0,
        T_air_F      = 35.0,
    )

    print("Running cycle solver...")
    sol = solve_cycle(test_specs, test_cond)

    if sol.converged:
        print(f"\n=== CYCLE SOLVER RESULT ===")
        print(f"T_evap  = {sol.T_evap_F:6.1f}°F   P_evap = {sol.P_evap_psig:6.1f} PSIG")
        print(f"T_cond  = {sol.T_cond_F:6.1f}°F   P_cond = {sol.P_cond_psig:6.1f} PSIG")
        print(f"T_disch = {sol.T_disch_F:6.1f}°F   PR     = {sol.PR:5.2f}")
        print(f"SH      = {sol.SH_F:6.1f}°F   SC     = {sol.SC_F:6.1f}°F")
        print(f"m_dot   = {sol.m_dot_lbhr:6.1f} lb/hr  eta_vol= {sol.eta_vol:.3f}")
        print(f"Q_evap  = {sol.Q_evap_btu_hr/1000:5.2f} kBTU/hr  ({sol.Q_evap_btu_hr/12000:.2f} tons)")
        print(f"W_comp  = {sol.W_comp_kW:.3f} kW")
        print(f"COP     = {sol.COP:.2f}")
        print(f"T_water_out = {sol.T_water_out_F:.1f}°F")
        print(f"h1={sol.h1:.1f} h2={sol.h2:.1f} h3={sol.h3:.1f} h4={sol.h4:.1f} kJ/kg")
    else:
        print(f"FAILED: {sol.error_msg}")
