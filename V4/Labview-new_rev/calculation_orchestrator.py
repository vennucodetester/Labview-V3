"""
calculation_orchestrator.py

Orchestrates the complete 8-point cycle calculation using port_resolver and calculation_engine.
This module bridges the diagram model with the calculation engine.
"""

from typing import Dict, Optional, List
import pandas as pd
from port_resolver import resolve_mapped_sensor, get_sensor_value
from calculation_engine import (
    calculate_row_performance,
)


def gather_compressor_specs(data_manager) -> Dict[str, Optional[float]]:
    """
    Gather compressor specifications from diagram and ports.

    Returns dict with keys: displacement_cm3, speed_rpm, vol_eff
    """
    model = data_manager.diagram_model
    components = model.get('components', {})

    specs = {}

    # Find Compressor
    for comp_id, comp in components.items():
        if comp.get('type') == 'Compressor':
            props = comp.get('properties', {})

            # Get displacement and vol_eff from properties
            specs['displacement_cm3'] = props.get('displacement_cm3')
            specs['vol_eff'] = props.get('vol_eff', 0.85)

            # Get RPM from mapped sensor
            sensor = resolve_mapped_sensor(model, 'Compressor', comp_id, 'RPM')
            val = get_sensor_value(data_manager, sensor)
            if val is not None:
                specs['speed_rpm'] = val
            else:
                # Fallback to property if sensor not mapped
                specs['speed_rpm'] = props.get('speed_rpm')

            break  # Assume single compressor

    return specs


# =========================================================================
# NEW UNIFIED BATCH PROCESSING ENGINE
# =========================================================================


def _detect_system_type(diagram_model: dict) -> str:
    """Return 'cassette' if multiple compressors exist, else 'shared'.

    Cassette units each have their own independent refrigeration loop
    (Compressor + Condenser + TXV + Evaporator) and cannot share a single
    P_suc/P_disch value.  The presence of more than one Compressor component
    in the diagram is the reliable indicator.
    """
    comps = diagram_model.get('components', {}) if diagram_model else {}
    n_compressors = sum(1 for c in comps.values()
                        if (c or {}).get('type') == 'Compressor')
    return 'cassette' if n_compressors > 1 else 'shared'


def _build_required_sensor_roles(module_labels: list) -> dict:
    """Build the REQUIRED_SENSOR_ROLES dict dynamically from the actual module labels.

    This replaces the old hard-coded REQUIRED_SENSOR_ROLES constant so that
    any number/combination of modules (Left, Center, Right, or any future
    label) is handled correctly.

    The coil-inlet key is always T_1b-{abbrev} — the T_1c-rh anomaly no longer
    exists; old sessions are migrated on load by _migrate_sensor_role_keys().
    The coil-outlet key is always T_2a-{ABBREV} (uppercase) for all modules.
    """
    from circuit_semantics import module_abbrev, txv_outlet_key, coil_outlet_key

    roles = {
        'P_suc':          [('Compressor', 'SP')],
        'P_disch':        [('Compressor', 'DP')],
        'RPM':            [('Compressor', 'RPM')],
        'T_2b':           [('Compressor', 'inlet')],
        'T_3a':           [('Compressor', 'outlet')],
        'T_3b':           [('Condenser',  'inlet')],
        'T_4a':           [('Condenser',  'outlet')],
        'T_waterin':      [('Condenser',  'water_inlet')],
        'T_waterout':     [('Condenser',  'water_outlet')],
        'Cond.water.out': [('Condenser',  'water_out_temp')],
        'Cond.water.in':  [('Condenser',  'water_in_temp')],
        'GPM_water':      [('Condenser',  'water_flow_gpm')],
    }

    for label in module_labels:
        ab    = module_abbrev(label)
        props = {'circuit_label': label}
        # T_1a: TXV outlet (dist_outlet, pre-coil)
        roles[f'T_1a-{ab}']          = [('TXV',        'outlet',           props)]
        # T_1b: Evap coil inlet (TXV outlet side / evap dist_inlet)
        roles[txv_outlet_key(label)]  = [('Evaporator', 'inlet_circuit_1',  props)]
        # T_2a: Evap coil outlet
        roles[coil_outlet_key(label)] = [('Evaporator', 'outlet_circuit_1', props)]
        # T_4b: TXV inlet (liquid line, pre-TXV)
        roles[f'T_4b-{ab}']          = [('TXV',        'inlet',            props)]

    return roles


def _build_cassette_unit_sensor_map(
        diagram_model: dict,
        label: str,
        input_columns: set,
        resolve_df_column,
) -> dict:
    """Build a complete sensor_map for one cassette unit identified by circuit_label.

    Each cassette unit is an independent refrigeration loop with its own
    Compressor, Condenser, TXV and Evaporator.  We locate each component by
    matching its ``circuit_label`` property to *label*, then resolve the port
    sensor for every required role.

    Returns a sensor_map dict suitable for passing to calculate_row_performance.
    """
    from circuit_semantics import module_abbrev, txv_outlet_key, coil_outlet_key

    comps = diagram_model.get('components', {})
    sm: dict = {}
    ab = module_abbrev(label)

    sp_map = diagram_model.get('sensor_points', {})

    def _rms(comp_type, comp_id, port):
        role_key = f"{comp_type}.{comp_id}.{port}"
        if role_key in sp_map and not sp_map[role_key].get('enabled', True):
            return None
        return resolve_df_column(
            resolve_mapped_sensor(diagram_model, comp_type, comp_id, port)
        )

    # --- Compressor (matched by circuit_label) ---
    for comp_id, comp in comps.items():
        if comp.get('type') == 'Compressor' and \
                comp.get('properties', {}).get('circuit_label') == label:
            for role, port in [('P_suc', 'SP'), ('P_disch', 'DP'), ('RPM', 'RPM'),
                                ('T_2b', 'inlet'), ('T_3a', 'outlet')]:
                col = _rms('Compressor', comp_id, port)
                if col:
                    sm[role] = col
            break

    # --- Condenser (matched by circuit_label) ---
    for comp_id, comp in comps.items():
        if comp.get('type') == 'Condenser' and \
                comp.get('properties', {}).get('circuit_label') == label:
            for role, port in [('T_3b', 'inlet'), ('T_4a', 'outlet'),
                                ('T_waterin', 'water_inlet'),
                                ('T_waterout', 'water_outlet'),
                                ('Cond.water.out', 'water_out_temp'),
                                ('Cond.water.in', 'water_in_temp'),
                                ('GPM_water', 'water_flow_gpm')]:
                col = _rms('Condenser', comp_id, port)
                if col:
                    sm[role] = col
            break

    # --- TXV (matched by circuit_label) ---
    for comp_id, comp in comps.items():
        if comp.get('type') == 'TXV' and \
                comp.get('properties', {}).get('circuit_label') == label:
            col_out = _rms('TXV', comp_id, 'outlet')
            col_in  = _rms('TXV', comp_id, 'inlet')
            if col_out:
                sm[f'T_1a-{ab}'] = col_out
            if col_in:
                sm[f'T_4b-{ab}'] = col_in
            break

    # --- Evaporator (matched by circuit_label — average across all circuits) ---
    t1b_key = txv_outlet_key(label)   # e.g. T_1b-lh
    t2a_key = coil_outlet_key(label)  # e.g. T_2a-LH
    for comp_id, comp in comps.items():
        if comp.get('type') == 'Evaporator' and \
                comp.get('properties', {}).get('circuit_label') == label:
            props   = comp.get('properties', {})
            try:
                circuits = int(props.get('circuits', 1) or 1)
            except Exception:
                circuits = 1

            in_cols:  List[str] = []
            out_cols: List[str] = []
            for i in range(1, circuits + 1):
                ic = _rms('Evaporator', comp_id, f'inlet_circuit_{i}')
                oc = _rms('Evaporator', comp_id, f'outlet_circuit_{i}')
                if ic:
                    in_cols.append(ic)
                if oc:
                    out_cols.append(oc)

            if in_cols:
                if len(in_cols) > 1:
                    sm[f'_avg_{t1b_key}'] = in_cols
                else:
                    sm[t1b_key] = in_cols[0]
            if out_cols:
                if len(out_cols) > 1:
                    sm[f'_avg_{t2a_key}'] = out_cols
                else:
                    sm[t2a_key] = out_cols[0]
            break

    return sm


def _find_sensor_for_role(model: Dict, role_def: tuple) -> Optional[str]:
    """
    Helper to find the first mapped sensor for a given role definition.

    Args:
        model: Diagram model dict
        role_def: Tuple of (ComponentType, PortName) or (ComponentType, PortName, {props})

    Returns:
        Sensor name (CSV column name) or None
    """
    components = model.get('components', {})

    role_comp_type = role_def[0]
    role_port = role_def[1]
    role_props = role_def[2] if len(role_def) > 2 else {}

    for comp_id, comp in components.items():
        comp_type = comp.get('type')
        props = comp.get('properties', {})

        # Check component type
        if comp_type != role_comp_type:
            continue

        # Check if properties match (e.g., circuit_label)
        props_match = True
        if role_props:
            for key, val in role_props.items():
                if props.get(key) != val:
                    props_match = False
                    break

        if props_match:
            # Found matching component, resolve the sensor
            sensor = resolve_mapped_sensor(model, comp_type, comp_id, role_port)
            if sensor:
                # Respect sensor_points enable/disable
                role_key = f"{comp_type}.{comp_id}.{role_port}"
                sp = model.get('sensor_points', {})
                if role_key in sp and not sp[role_key].get('enabled', True):
                    return None
                return sensor

    return None


def run_batch_processing(
    data_manager,
    input_dataframe: pd.DataFrame
) -> pd.DataFrame:
    """
    The main entry point for the "Calculations" tab.

    Implements the complete two-step calculation process:
    - Step 1: Resolve sensor map from diagram model
    - Step 2: Apply row-by-row performance calculations for each timestamp

    Supports three system layouts:
    - shared (modular / non-modular): one compressor/condenser shared by all modules
    - cassette: each unit has its own independent compressor/condenser/TXV/evaporator

    Args:
        data_manager: DataManager instance with diagram_model and rated_inputs
        input_dataframe: Raw CSV data (or filtered data)

    Returns:
        DataFrame with all calculated columns
    """
    print(f"[BATCH PROCESSING] Starting batch processing on {len(input_dataframe)} rows...")

    # === SYSTEM SPECS ===
    rated_inputs = data_manager.rated_inputs
    refrigerant  = data_manager.refrigerant or 'R290'
    comp_specs   = {'gpm_water': rated_inputs.get('gpm_water')}
    print(f"[BATCH PROCESSING] Water flow rate: {comp_specs.get('gpm_water', 'Not set')} GPM")

    # Compressor specs (displacement/speed from the Compressor component) and
    # the Step-1 volumetric efficiency — used by the engine for the
    # displacement-based mass-flow cross-check (m_dot_disp column).
    try:
        comp_specs.update({k: v for k, v in gather_compressor_specs(data_manager).items()
                           if v is not None})
        from calculation_engine import calculate_volumetric_efficiency
        eta_info = calculate_volumetric_efficiency(rated_inputs, refrigerant)
        eta_vol = eta_info.get('eta_vol', 0.85)
        if not (0.3 <= eta_vol <= 1.0):
            print(f"[BATCH PROCESSING] WARNING: calculated eta_vol={eta_vol:.3f} "
                  f"is implausible — check rated inputs; using 0.85")
            eta_vol = 0.85
        comp_specs['eta_vol'] = eta_vol
        print(f"[BATCH PROCESSING] eta_vol = {comp_specs['eta_vol']:.3f} "
              f"({eta_info.get('method', 'unknown')})")
    except Exception as e:
        print(f"[BATCH PROCESSING] Compressor spec gathering failed (cross-check disabled): {e}")

    # === DIAGRAM MODEL ===
    diagram_model  = data_manager.diagram_model
    input_columns  = set(input_dataframe.columns if input_dataframe is not None else [])

    # Robust column resolver: tolerate whitespace/case differences between
    # diagram mappings and DataFrame headers.
    normalized_to_actual: dict = {}
    for col in input_columns:
        try:
            key = str(col).strip().lower()
        except Exception:
            continue
        if key and key not in normalized_to_actual:
            normalized_to_actual[key] = col

    def resolve_df_column(mapped_name: Optional[str]) -> Optional[str]:
        if not mapped_name:
            return None
        if mapped_name in input_columns:
            return mapped_name
        stripped = mapped_name.strip()
        if stripped in input_columns:
            return stripped
        return normalized_to_actual.get(stripped.lower())

    # === DETECT SYSTEM TYPE AND MODULE LABELS ===
    from circuit_semantics import get_all_module_labels, module_abbrev
    module_labels = get_all_module_labels(diagram_model)
    system_type   = _detect_system_type(diagram_model)
    print(f"[BATCH PROCESSING] System type: {system_type}, modules: {module_labels}")

    # =========================================================
    # CASSETTE PATH: per-unit independent refrigeration loops
    # =========================================================
    if system_type == 'cassette':
        if not module_labels:
            print("[BATCH PROCESSING] ERROR: cassette detected but no circuit_label modules found.")
            return pd.DataFrame()

        all_unit_dfs: List[pd.DataFrame] = []

        for label in module_labels:
            ab = module_abbrev(label)
            print(f"[BATCH PROCESSING] Building cassette sensor map for unit: {label}")
            unit_sm = _build_cassette_unit_sensor_map(
                diagram_model, label, input_columns, resolve_df_column)
            print(f"[BATCH PROCESSING]   {label} sensor map: {unit_sm}")

            unit_df = input_dataframe.apply(
                calculate_row_performance,
                axis=1,
                sensor_map=unit_sm,
                comp_specs=comp_specs,
                refrigerant=refrigerant,
                module_labels=[label],
                system_type='cassette',
            )

            # Rename per-unit columns that would collide when merging.
            # This covers:
            #  - Temperatures / pressures from the shared compressor/condenser block
            #  - Mass flow and capacity
            #  - Hidden h-columns (h_2b, h_3a, h_4a) used by the audit report
            #  - Per-module P-h columns (h_4b_LH, h_2a_LH …) — already suffixed with
            #    the module abbreviation but still need a unit suffix to avoid clashes
            #    if two cassette units happen to produce a column with the same label.
            ab_u = module_abbrev(label, upper=True)
            rename_map = {
                # Raw temperatures / pressures
                'T_2b':      f'T_2b-{ab}',
                'T_3a':      f'T_3a-{ab}',
                'T_3b':      f'T_3b-{ab}',
                'T_4a':      f'T_4a-{ab}',
                'P_suction': f'P_suc-{ab}',
                'P_disch':   f'P_disch-{ab}',
                # Derived shared-block columns
                'T_sat.comp.in': f'T_sat.comp.in-{ab}',
                'S.H_total':     f'S.H_total-{ab}',
                'D_comp.in':     f'D_comp.in-{ab}',
                'H_comp.in':     f'H_comp.in-{ab}',
                'S_comp.in':     f'S_comp.in-{ab}',
                'T_sat.cond':    f'T_sat.cond-{ab}',
                'S.C':           f'S.C-{ab}',
                'T_waterin':     f'T_waterin-{ab}',
                'T_waterout':    f'T_waterout-{ab}',
                'rpm':           f'rpm-{ab}',
                # Mass flow and capacity
                'm_dot':       f'm_dot-{ab}',
                'qc':          f'qc-{ab}',
                'gpm':         f'gpm-{ab}',
                'm_dot_disp':  f'm_dot_disp-{ab}',
                'qc_coils':    f'qc_coils-{ab}',
                'Q_line_gain': f'Q_line_gain-{ab}',
                'W_comp':      f'W_comp-{ab}',
                'COP':         f'COP-{ab}',
                'EER':         f'EER-{ab}',
                'eta_is':      f'eta_is-{ab}',
                # Hidden h-columns (audit report)
                'h_2b': f'h_2b-{ab}',
                'h_3a': f'h_3a-{ab}',
                'h_4a': f'h_4a-{ab}',
                # Per-module P-h columns — a cassette unit runs with a single label so
                # these will carry that label's abbreviation; suffix with unit ab to be safe
                f'h_4b_{ab_u}': f'h_4b_{ab_u}-{ab}',
                f'h_2a_{ab_u}': f'h_2a_{ab_u}-{ab}',
                # P_suc/P_cond are in Pa (internal)
                'P_suc':  f'P_suc_pa-{ab}',
                'P_cond': f'P_cond_pa-{ab}',
            }
            unit_df = unit_df.rename(
                columns={k: v for k, v in rename_map.items() if k in unit_df.columns}
            )
            all_unit_dfs.append(unit_df)

        # Merge: concat column-wise (all DataFrames share the same row index)
        results_df = pd.concat(all_unit_dfs, axis=1)
        print(f"[BATCH PROCESSING] Cassette calculation complete! "
              f"{len(results_df)} rows, {len(results_df.columns)} columns.")
        return results_df

    # =========================================================
    # SHARED COMPRESSOR PATH: modular / non-modular
    # =========================================================
    sensor_map: dict = {}

    # Pressure sensors via port_resolver (supports inline Sensors + Compressor SP/DP)
    from port_resolver import find_suction_pressure_sensor, find_discharge_pressure_sensor
    sp_col = resolve_df_column(find_suction_pressure_sensor(diagram_model))
    dp_col = resolve_df_column(find_discharge_pressure_sensor(diagram_model))
    if sp_col:
        sensor_map['P_suc']   = sp_col
    if dp_col:
        sensor_map['P_disch'] = dp_col

    # Build dynamic required roles from actual module labels
    # Fall back to single LH-only if no modules detected (non-modular)
    effective_labels = module_labels if module_labels else ['Left']
    required_roles   = _build_required_sensor_roles(effective_labels)

    for key, role_defs in required_roles.items():
        # Skip pressures already set above
        if key in ('P_suc', 'P_disch') and key in sensor_map:
            continue
        for role_def in role_defs:
            actual_col = resolve_df_column(_find_sensor_for_role(diagram_model, role_def))
            if actual_col:
                sensor_map[key] = actual_col
                break

        if key not in sensor_map:
            print(f"[BATCH PROCESSING] WARNING: No sensor mapped for role '{key}' "
                  f"(or column missing in input data)")

    # Multi-circuit averaging for evaporator inlets/outlets
    # (override the single-circuit entry from required_roles with averaged lists)
    components = diagram_model.get('components', {})
    for label in effective_labels:
        from circuit_semantics import txv_outlet_key, coil_outlet_key
        t1b_key = txv_outlet_key(label)   # T_1b-lh / T_1b-ctr / T_1b-rh
        t2a_key = coil_outlet_key(label)  # T_2a-LH / T_2a-CTR / T_2a-RH

        for comp_id, comp in components.items():
            if comp.get('type') == 'Evaporator' and \
                    comp.get('properties', {}).get('circuit_label') == label:
                props = comp.get('properties', {})
                try:
                    circuits = int(props.get('circuits', 1) or 1)
                except Exception:
                    circuits = 1

                if circuits <= 1:
                    break  # Single circuit already handled by required_roles lookup

                inlet_cols:  List[str] = []
                outlet_cols: List[str] = []
                for i in range(1, circuits + 1):
                    ic = resolve_df_column(
                        resolve_mapped_sensor(diagram_model, 'Evaporator', comp_id, f'inlet_circuit_{i}'))
                    oc = resolve_df_column(
                        resolve_mapped_sensor(diagram_model, 'Evaporator', comp_id, f'outlet_circuit_{i}'))
                    if ic:
                        inlet_cols.append(ic)
                    if oc:
                        outlet_cols.append(oc)

                if inlet_cols:
                    sensor_map[f'_avg_{t1b_key}'] = inlet_cols
                if outlet_cols:
                    sensor_map[f'_avg_{t2a_key}'] = outlet_cols
                break

    # Non-modular single-coil fallback:
    # If no coil mappings were found for any module, but there is exactly one
    # Evaporator and one TXV (circuit_label == None), map them into LH roles.
    from circuit_semantics import txv_outlet_key as _tok, coil_outlet_key as _cok
    _lh_presence = (
        'T_1a-lh', 'T_4b-lh', _tok('Left'), _cok('Left'),
        f'_avg_{_tok("Left")}', f'_avg_{_cok("Left")}',
    )
    has_any_coil_mapping = any(k in sensor_map for k in _lh_presence) or any(
        k in sensor_map
        for label in (module_labels or [])
        for k in (f'T_1a-{module_abbrev(label)}', f'T_4b-{module_abbrev(label)}',
                  _tok(label), _cok(label))
    )

    if not has_any_coil_mapping:
        evaps = [(cid, c) for cid, c in components.items()
                 if (c or {}).get('type') == 'Evaporator']
        txvs  = [(cid, c) for cid, c in components.items()
                 if (c or {}).get('type') == 'TXV']

        if len(evaps) == 1 and len(txvs) == 1:
            evap_id, evap_comp = evaps[0]
            txv_id,  _txv_comp = txvs[0]

            try:
                circuits = int((evap_comp.get('properties', {}) or {}).get('circuits', 1) or 1)
            except Exception:
                circuits = 1

            in_cols: List[str] = []
            out_cols: List[str] = []
            for i in range(1, circuits + 1):
                ic = resolve_df_column(
                    resolve_mapped_sensor(diagram_model, 'Evaporator', evap_id, f'inlet_circuit_{i}'))
                oc = resolve_df_column(
                    resolve_mapped_sensor(diagram_model, 'Evaporator', evap_id, f'outlet_circuit_{i}'))
                if ic:
                    in_cols.append(ic)
                if oc:
                    out_cols.append(oc)

            if in_cols:
                if len(in_cols) > 1:
                    sensor_map['_avg_T_1b-lh'] = in_cols
                else:
                    sensor_map['T_1b-lh'] = in_cols[0]
            if out_cols:
                if len(out_cols) > 1:
                    sensor_map['_avg_T_2a-LH'] = out_cols
                else:
                    sensor_map['T_2a-LH'] = out_cols[0]

            txv_out_col = resolve_df_column(
                resolve_mapped_sensor(diagram_model, 'TXV', txv_id, 'outlet'))
            txv_in_col  = resolve_df_column(
                resolve_mapped_sensor(diagram_model, 'TXV', txv_id, 'inlet'))
            if txv_out_col:
                sensor_map['T_1a-lh'] = txv_out_col
            if txv_in_col:
                sensor_map['T_4b-lh'] = txv_in_col

            # Single-coil: treat as one LH module
            effective_labels = ['Left']
            print("[BATCH PROCESSING] Single-coil fallback applied: "
                  "mapped 1 Evaporator + 1 TXV into LH roles.")
        else:
            print(
                "[BATCH PROCESSING] Single-coil fallback skipped: no coil mappings found, "
                f"but evaporators={len(evaps)}, txvs={len(txvs)}. "
                "Ensure circuit_label properties are set for modular layouts."
            )

    print(f"[BATCH PROCESSING] Sensor map built with {len(sensor_map)} valid mappings")
    print(f"[BATCH PROCESSING] Sensor map: {sensor_map}")

    # === ROW-BY-ROW PROCESSING ===
    print("[BATCH PROCESSING] Starting row-by-row calculation...")

    results_df = input_dataframe.apply(
        calculate_row_performance,
        axis=1,
        sensor_map=sensor_map,
        comp_specs=comp_specs,
        refrigerant=refrigerant,
        module_labels=effective_labels,
        system_type='shared',
    )

    print(f"[BATCH PROCESSING] Row-by-row calculation complete!")
    print(f"[BATCH PROCESSING] Output DataFrame has {len(results_df)} rows "
          f"and {len(results_df.columns)} columns")
    print(f"[BATCH PROCESSING] Output columns: {list(results_df.columns)}")

    return results_df


def run_cycle_prediction(diagram_model: dict,
                         processed_df,
                         rated_inputs: dict = None):
    """
    Run the steady-state cycle solver against the current diagram model
    and processed sensor data.

    Called after run_batch_processing() by the Calculations widget.
    The returned CycleSolution is passed to run_all_diagnostics() so the
    PV-1 scenario can compare predicted vs actual without re-running the solver.

    Returns
    -------
    CycleSolution  — with .converged=False if the solver could not run.
    """
    try:
        from cycle_solver import (
            extract_specs_from_model, extract_conditions_from_df, solve_cycle,
            CycleSolution,
        )
        specs      = extract_specs_from_model(diagram_model)
        conditions = extract_conditions_from_df(processed_df, rated_inputs or {})
        solution   = solve_cycle(specs, conditions)

        if solution.converged:
            print(f"[CYCLE SOLVER] Converged: "
                  f"T_evap={solution.T_evap_F:.1f}°F  "
                  f"T_cond={solution.T_cond_F:.1f}°F  "
                  f"Q_evap={solution.Q_evap_btu_hr/12000:.2f} tons  "
                  f"COP={solution.COP:.2f}")
        else:
            print(f"[CYCLE SOLVER] Did not converge: {solution.error_msg}")

        return solution

    except Exception as exc:
        print(f"[CYCLE SOLVER] Exception: {exc}")
        try:
            from cycle_solver import CycleSolution
            s = CycleSolution()
            s.error_msg = str(exc)
            return s
        except Exception:
            # Return a minimal object that diagnostics can handle gracefully
            class _FallbackSolution:
                converged = False
                error_msg = str(exc)
            return _FallbackSolution()
