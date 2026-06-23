"""
calculation_engine.py

Pure calculation logic for refrigeration cycle P-h points and performance metrics.
Decoupled from any UI; takes normalized inputs and returns structured results.

Assumptions:
- Pressures provided in Pascals (absolute)
- Temperatures provided in Kelvin
- Default refrigerant: R410A
"""

from typing import Dict, List, Optional, Tuple
import pandas as pd

try:
    import CoolProp.CoolProp as CP
except Exception:  # pragma: no cover - CoolProp may not be available in some environments
    CP = None  # type: ignore


# --- Helper Functions for Unit Conversion ---
def f_to_k(temp_f: float) -> float:
    """Converts Fahrenheit to Kelvin."""
    return (temp_f + 459.67) * 5.0 / 9.0

def psig_to_pa(pressure_psig: float) -> float:
    """Converts PSIG (gauge) to Pascals (absolute)."""
    return (pressure_psig + 14.7) * 6894.76


# =========================================================================
# NEW UNIFIED CALCULATION ENGINE (from goal.md)
# Implements the two-step calculation process from Calculations-DDT.txt
# =========================================================================

def hz_to_rph(hz: float) -> float:
    """Convert Hz to revolutions per hour."""
    return hz * 3600.0


def ft3_to_m3(ft3: float) -> float:
    """Convert cubic feet to cubic meters."""
    if ft3 is None:
        return 0.0
    return ft3 * 0.0283168


def calculate_volumetric_efficiency(rated_inputs: Dict, refrigerant: str = 'R290') -> Dict:
    """
    Performs the "Step 1" calculation from Calculations-DDT.txt / goal.md
    to find the constant volumetric efficiency (eta_vol).

    This is a one-time calculation based on user manual inputs (rated values).

    Goal-2C: Implements graceful degradation - returns default eta_vol (0.85)
    with warnings if rated inputs are missing.

    Args:
        rated_inputs: Dict with keys:
            - m_dot_rated_lbhr: Rated mass flow rate (lbm/hr)
            - hz_rated: Rated compressor speed (Hz)
            - disp_ft3: Compressor displacement (ft³)
            - rated_evap_temp_f: Rated evaporator temperature (°F)
            - rated_return_gas_temp_f: Rated return gas temperature (°F)
        refrigerant: Refrigerant name (default 'R290')

    Returns:
        Dict with:
        - eta_vol: float (calculated or default 0.85)
        - method: 'calculated' | 'default'
        - warnings: list of warning messages (empty if calculated)
        - (other intermediate values if calculated successfully)
    """
    if CP is None:
        return {'error': 'CoolProp not available'}

    # 1. Get User Inputs
    m_dot_rated_lb_hr = rated_inputs.get('m_dot_rated_lbhr')
    rated_evap_f = rated_inputs.get('rated_evap_temp_f')
    rated_return_f = rated_inputs.get('rated_return_gas_temp_f')
    rated_disp_ft3 = rated_inputs.get('disp_ft3')
    rated_hz = rated_inputs.get('hz_rated')

    # Check if all required inputs are present.
    # NOTE: temperatures use `is None` — 0 °F is a legitimate rating point
    # for low-temp systems and must not be treated as "missing".
    missing = []
    if not m_dot_rated_lb_hr:
        missing.append('Rated Mass Flow Rate')
    if not rated_hz:
        missing.append('Rated Compressor Speed')
    if not rated_disp_ft3:
        missing.append('Compressor Displacement')
    if rated_evap_f is None:
        missing.append('Rated Evaporator Temperature')
    if rated_return_f is None:
        missing.append('Rated Return Gas Temperature')

    # GRACEFUL DEGRADATION: Use default if inputs missing
    if missing:
        return {
            'eta_vol': 0.85,
            'method': 'default',
            'warnings': [
                f"Missing rated inputs: {', '.join(missing)}",
                "Using default volumetric efficiency (0.85)",
                "Mass flow and cooling capacity calculations will be approximate"
            ]
        }

    # Try to calculate
    try:
        # 2. Calculate Theoretical Mass Flow (m_dot_th)
        # Get saturation pressure at rated evaporator temperature
        rated_evap_k = f_to_k(rated_evap_f)
        P_rated_sat = CP.PropsSI('P', 'T', rated_evap_k, 'Q', 0, refrigerant)

        # Get density at rated return gas temperature and saturation pressure
        rated_return_k = f_to_k(rated_return_f)
        dens_rated_kg_m3 = CP.PropsSI('D', 'T', rated_return_k, 'P', P_rated_sat, refrigerant)
        dens_rated_lb_ft3 = dens_rated_kg_m3 * 0.062428  # Convert to lb/ft³

        # Calculate RPH (revolutions per hour)
        rph = hz_to_rph(rated_hz)

        # Theoretical mass flow
        m_dot_th_lb_hr = dens_rated_lb_ft3 * rph * rated_disp_ft3

        # 3. Calculate Volumetric Efficiency
        if m_dot_th_lb_hr == 0:
            # GRACEFUL DEGRADATION: Calculation failed, use default
            return {
                'eta_vol': 0.85,
                'method': 'default',
                'warnings': [
                    "Theoretical mass flow is zero - cannot calculate eta_vol",
                    "Using default volumetric efficiency (0.85)"
                ]
            }

        eta_vol = m_dot_rated_lb_hr / m_dot_th_lb_hr

        return {
            'eta_vol': eta_vol,
            'method': 'calculated',
            'warnings': [],
            'm_dot_rated_lb_hr': m_dot_rated_lb_hr,
            'm_dot_th_lb_hr': m_dot_th_lb_hr,
            'dens_rated_lb_ft3': dens_rated_lb_ft3,
            'dens_rated_kg_m3': dens_rated_kg_m3,
            'P_rated_sat_pa': P_rated_sat,
            'rph': rph,
        }
    except Exception as e:
        # GRACEFUL DEGRADATION: Exception occurred, use default
        return {
            'eta_vol': 0.85,
            'method': 'default',
            'warnings': [
                f"Error calculating eta_vol: {str(e)}",
                "Using default volumetric efficiency (0.85)"
            ]
        }


def calculate_row_performance(
    row: pd.Series,
    sensor_map: Dict[str, str],
    comp_specs: Dict,
    refrigerant: str = 'R290',
    module_labels: Optional[List[str]] = None,
    system_type: str = 'shared',
) -> pd.Series:
    """
    Performs the "Step 2" calculation from Calculations-DDT.txt
    on a single row of data.

    Produces all calculated columns for any number of evaporator modules and
    for both shared-compressor (modular / non-modular) and cassette layouts.

    Args:
        row:          Single row from DataFrame (pandas Series)
        sensor_map:   Dict mapping internal role keys to CSV column names
        comp_specs:   Dict with 'gpm_water' key
        refrigerant:  Refrigerant name (default 'R290')
        module_labels: List of module labels present in diagram
                       e.g. ['Left', 'Center', 'Right'] or ['Left'] or ['LH', 'RH']
                       Defaults to ['Left', 'Center', 'Right'] for backward compat.
        system_type:  'shared' (one compressor) | 'cassette' (per-unit compressor)

    Returns:
        pandas Series with all calculated values PLUS P-h diagram columns
    """
    from circuit_semantics import module_abbrev, txv_outlet_key, coil_outlet_key

    if module_labels is None:
        module_labels = ['Left', 'Center', 'Right']   # backward-compat default

    if CP is None:
        return pd.Series({'error': 'CoolProp not available'})

    results = {}

    try:
        # ── Helper: safely get a sensor value from the row ──────────────────
        def get_val(key):
            col_name_or_list = sensor_map.get(key)
            if col_name_or_list is None:
                return None
            if isinstance(col_name_or_list, list):
                values = [row.get(c) for c in col_name_or_list if row.get(c) is not None]
                return sum(values) / len(values) if values else None
            return row.get(col_name_or_list)

        def k_to_f(k):
            return (k - 273.15) * 9.0 / 5.0 + 32.0

        # ── 1. PRESSURES ────────────────────────────────────────────────────
        p_suc_psig   = get_val('P_suc')
        p_disch_psig = get_val('P_disch')

        if p_suc_psig is None or p_disch_psig is None:
            return pd.Series({
                'error': ('Missing pressure sensors - '
                          'Please map suction and discharge pressure sensors in the Diagram tab')
            })

        p_suc_pa   = psig_to_pa(p_suc_psig)
        p_disch_pa = psig_to_pa(p_disch_psig)

        # Superheat must be measured against the DEW point (Q=1) and
        # subcooling against the BUBBLE point (Q=0).  Identical for pure
        # R290, but required for any zeotropic blend with glide.
        t_sat_suc_k   = CP.PropsSI('T', 'P', p_suc_pa,   'Q', 1, refrigerant)
        t_sat_disch_k = CP.PropsSI('T', 'P', p_disch_pa, 'Q', 0, refrigerant)

        # ── 2. PER-MODULE COIL CALCULATIONS (dynamic loop) ─────────────────
        # For each module we compute and store:
        #   h_2a_by_label[label]  — evap-outlet enthalpy (J/kg), may be None
        #   h_4b_by_label[label]  — TXV-inlet enthalpy   (J/kg), may be None
        h_2a_by_label: dict = {}
        h_4b_by_label: dict = {}

        for label in module_labels:
            ab    = module_abbrev(label)          # 'lh' / 'ctr' / 'rh'
            ab_up = module_abbrev(label, upper=True)  # 'LH' / 'CTR' / 'RH'

            t1a_key = f'T_1a-{ab}'
            t1b_key = txv_outlet_key(label)       # T_1b-lh / T_1b-ctr / T_1b-rh (no anomaly)
            t2a_key = coil_outlet_key(label)      # T_2a-LH / T_2a-CTR / T_2a-RH
            t4b_key = f'T_4b-{ab}'

            # Fetch sensor values (prefer averaged list versions)
            t_1a_f = get_val(t1a_key)
            t_1b_f = get_val(f'_avg_{t1b_key}') if f'_avg_{t1b_key}' in sensor_map \
                     else get_val(t1b_key)
            t_2a_f = get_val(f'_avg_{t2a_key}') if f'_avg_{t2a_key}' in sensor_map \
                     else get_val(t2a_key)
            t_4b_f = get_val(t4b_key)

            # Store raw temperatures
            if t_1a_f is not None:
                results[t1a_key] = t_1a_f
            if t_1b_f is not None:
                results[t1b_key] = t_1b_f
            if t_2a_f is not None:
                results[t2a_key] = t_2a_f

            # ── Evap outlet thermodynamics ───────────────────────────────────
            h_2a = None
            if t_2a_f is not None:
                t_2a_k = f_to_k(t_2a_f)
                h_2a   = CP.PropsSI('H', 'T', t_2a_k, 'P', p_suc_pa, refrigerant)
                s_2a   = CP.PropsSI('S', 'T', t_2a_k, 'P', p_suc_pa, refrigerant)
                d_2a   = CP.PropsSI('D', 'T', t_2a_k, 'P', p_suc_pa, refrigerant)
                sh     = t_2a_k - t_sat_suc_k

                results[f'T_sat.{ab}']    = k_to_f(t_sat_suc_k)
                results[f'S.H_{ab} coil'] = sh * 9.0 / 5.0
                results[f'D_coil {ab}']   = d_2a
                results[f'H_coil {ab}']   = h_2a / 1000.0
                results[f'S_coil {ab}']   = s_2a / 1000.0
            h_2a_by_label[label] = h_2a

            # ── TXV inlet thermodynamics ─────────────────────────────────────
            h_4b = None
            if t_4b_f is not None:
                results[t4b_key] = t_4b_f
                t_4b_k = f_to_k(t_4b_f)
                h_4b   = CP.PropsSI('H', 'T', t_4b_k, 'P', p_disch_pa, refrigerant)
                subcool = t_sat_disch_k - t_4b_k

                results[f'T_sat.txv.{ab}'] = k_to_f(t_sat_disch_k)
                results[f'S.C-txv.{ab}']   = subcool * 9.0 / 5.0
                results[f'H_txv.{ab}']     = h_4b / 1000.0
            h_4b_by_label[label] = h_4b

        # ── 3. COMPRESSOR INLET (shared for 'shared' system; per-unit for cassette) ─
        t_2b_f = get_val('T_2b')
        t_3a_f = get_val('T_3a')
        t_3b_f = get_val('T_3b')
        t_4a_f = get_val('T_4a')
        # Condenser water temps: support both legacy and canonical key names
        # (explicit None checks — `or` would discard a legitimate 0.0 reading)
        t_waterin_f = get_val('T_waterin')
        if t_waterin_f is None:
            t_waterin_f = get_val('Cond.water.in')
        t_waterout_f = get_val('T_waterout')
        if t_waterout_f is None:
            t_waterout_f = get_val('Cond.water.out')

        h_2b, h_3a, h_3b, h_4a, rho_2b = None, None, None, None, None

        results['P_suction'] = p_suc_psig

        if t_2b_f is not None:
            results['T_2b'] = t_2b_f
            t_2b_k = f_to_k(t_2b_f)
            h_2b   = CP.PropsSI('H', 'T', t_2b_k, 'P', p_suc_pa, refrigerant)
            s_2b   = CP.PropsSI('S', 'T', t_2b_k, 'P', p_suc_pa, refrigerant)
            rho_2b = CP.PropsSI('D', 'T', t_2b_k, 'P', p_suc_pa, refrigerant)
            sh_total = t_2b_k - t_sat_suc_k

            results['T_sat.comp.in'] = k_to_f(t_sat_suc_k)
            results['S.H_total']     = sh_total * 9.0 / 5.0
            results['D_comp.in']     = rho_2b
            results['H_comp.in']     = h_2b / 1000.0
            results['S_comp.in']     = s_2b / 1000.0

        # ── 4. COMPRESSOR OUTLET ─────────────────────────────────────────────
        if t_3a_f is not None:
            results['T_3a'] = t_3a_f
            t_3a_k = f_to_k(t_3a_f)
            h_3a   = CP.PropsSI('H', 'T', t_3a_k, 'P', p_disch_pa, refrigerant)

        # ── 5. CONDENSER ─────────────────────────────────────────────────────
        if t_3b_f is not None:
            results['T_3b'] = t_3b_f
            t_3b_k = f_to_k(t_3b_f)
            h_3b   = CP.PropsSI('H', 'T', t_3b_k, 'P', p_disch_pa, refrigerant)

        results['P_disch'] = p_disch_psig

        if t_4a_f is not None:
            results['T_4a'] = t_4a_f
            t_4a_k = f_to_k(t_4a_f)
            h_4a   = CP.PropsSI('H', 'T', t_4a_k, 'P', p_disch_pa, refrigerant)
            subcool_cond = t_sat_disch_k - t_4a_k
            results['T_sat.cond'] = k_to_f(t_sat_disch_k)
            results['S.C']        = subcool_cond * 9.0 / 5.0

        if t_waterin_f is not None:
            results['T_waterin'] = t_waterin_f
        if t_waterout_f is not None:
            results['T_waterout'] = t_waterout_f

        # ── 6. TOTAL — mass flow and cooling capacity ────────────────────────
        # Measured per-row water GPM (Condenser water_flow_gpm sensor) takes
        # priority over the constant rated input — real flow varies, and a
        # constant GPM makes m_dot/qc swing wildly while the averages look fine.
        gpm_row = get_val('GPM_water')
        gpm_water = gpm_row if gpm_row is not None else comp_specs.get('gpm_water')
        if gpm_water is not None:
            results['gpm'] = gpm_water

        # Echo RPM back to results for table display.
        # For fixed-speed compressors this will be None → column shows '---' gracefully.
        # For cassette the orchestrator rename_map converts 'rpm' → 'rpm-{ab}'.
        speed_rpm = comp_specs.get('speed_rpm')
        if speed_rpm is not None:
            results['rpm'] = speed_rpm

        mass_flow_lbhr = None
        if gpm_water and t_waterin_f is not None and t_waterout_f is not None:
            delta_t_water_f = t_waterout_f - t_waterin_f

            # Condenser-side enthalpy drop: prefer the measured condenser
            # inlet (3b) when available — discharge-line heat loss between
            # 3a and 3b never reaches the water.  Fall back to the original
            # spec's assumption (3a ≈ 3b, adiabatic discharge line).
            h_cond_in = h_3b if h_3b is not None else h_3a

            if h_cond_in and h_4a:
                h_cond_in_btulb       = h_cond_in * 0.0004299
                h_4a_btulb            = h_4a * 0.0004299
                delta_h_cond_btulb    = h_cond_in_btulb - h_4a_btulb

                if delta_h_cond_btulb > 0:
                    q_water_btuhr  = 500.4 * gpm_water * delta_t_water_f
                    mass_flow_lbhr = q_water_btuhr / delta_h_cond_btulb
                    results['m_dot'] = mass_flow_lbhr

                    # System cooling capacity at the compressor (mixed flow —
                    # rigorous point for total-flow × enthalpy; includes
                    # suction-line heat gain by definition)
                    if h_2b:
                        h_4b_values = [h for h in h_4b_by_label.values()
                                       if h is not None]
                        if h_4b_values:
                            h_4b_avg          = sum(h_4b_values) / len(h_4b_values)
                            h_2b_btulb        = h_2b   * 0.0004299
                            h_4b_avg_btulb    = h_4b_avg * 0.0004299
                            delta_h_evap_btulb = h_2b_btulb - h_4b_avg_btulb
                            results['qc'] = mass_flow_lbhr * delta_h_evap_btulb

                            # Coil-side capacity (equal flow split assumed) and
                            # suction-line heat gain — their difference.
                            h_2a_values = [h for h in h_2a_by_label.values()
                                           if h is not None]
                            if h_2a_values:
                                h_2a_avg = sum(h_2a_values) / len(h_2a_values)
                                results['qc_coils'] = mass_flow_lbhr * (
                                    h_2a_avg - h_4b_avg) * 0.0004299
                                results['Q_line_gain'] = mass_flow_lbhr * (
                                    h_2b - h_2a_avg) * 0.0004299

        # ── 6b. CROSS-CHECK & COMPRESSOR HEALTH METRICS ─────────────────────
        # Displacement-based mass flow — independent of the water balance.
        # Disagreement between m_dot and m_dot_disp is itself a diagnostic
        # (valve leakage / vol-eff degradation vs water-side sensor error).
        disp_cm3 = comp_specs.get('displacement_cm3')
        eta_vol  = comp_specs.get('eta_vol') or comp_specs.get('vol_eff')
        if rho_2b is not None and disp_cm3 and speed_rpm and eta_vol:
            m_dot_disp_kgs = (rho_2b * (disp_cm3 * 1e-6)
                              * (speed_rpm / 60.0) * eta_vol)
            results['m_dot_disp'] = m_dot_disp_kgs * 2.20462 * 3600.0  # lb/hr

        # Isentropic efficiency from measured discharge temperature —
        # the most direct compressor-health metric (trend it over time).
        if h_2b is not None and h_3a is not None and (h_3a - h_2b) > 0:
            h_3a_is = CP.PropsSI('H', 'P', p_disch_pa, 'S', s_2b, refrigerant)
            results['eta_is'] = (h_3a_is - h_2b) / (h_3a - h_2b)

        # Refrigerant-side compressor work, COP and EER
        if mass_flow_lbhr and h_2b is not None and h_3a is not None:
            w_comp_btuhr = mass_flow_lbhr * (h_3a - h_2b) * 0.0004299
            results['W_comp'] = w_comp_btuhr
            qc_val = results.get('qc')
            if qc_val and w_comp_btuhr > 0:
                results['COP'] = qc_val / w_comp_btuhr
                results['EER'] = qc_val / (w_comp_btuhr / 3.41214)

        # ── 7. P-H DIAGRAM COLUMNS ───────────────────────────────────────────
        if h_2b is not None:
            results['h_2b'] = h_2b / 1000.0
        if h_3a is not None:
            results['h_3a'] = h_3a / 1000.0
        if h_3b is not None:
            results['h_3b'] = h_3b / 1000.0
        if h_4a is not None:
            results['h_4a'] = h_4a / 1000.0

        # Per-module P-h columns — generated dynamically for whatever modules exist
        for label, h_val in h_2a_by_label.items():
            if h_val is not None:
                results[f'h_2a_{module_abbrev(label, upper=True)}'] = h_val / 1000.0
        for label, h_val in h_4b_by_label.items():
            if h_val is not None:
                results[f'h_4b_{module_abbrev(label, upper=True)}'] = h_val / 1000.0

        # P-h diagram pressures in Pa
        results['P_suc']  = p_suc_pa
        results['P_cond'] = p_disch_pa

        return pd.Series(results)

    except Exception as e:
        print(f"Error processing row: {e}")
        import traceback
        traceback.print_exc()
        return pd.Series({'error': str(e)})


