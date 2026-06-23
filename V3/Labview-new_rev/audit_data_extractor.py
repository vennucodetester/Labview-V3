"""
Audit Data Extractor

Extracts and organizes thermodynamic state data from calculation results
for visual diagram rendering in the audit dialog.
"""

import math


class AuditDataExtractor:
    """Extract and organize thermodynamic state data for audit visualizations."""

    @staticmethod
    def safe_get(row_data, col_name, default=None):
        """Safely get value from row data, handling NaN and missing values."""
        try:
            if hasattr(row_data, 'get'):
                val = row_data.get(col_name, default)
            elif hasattr(row_data, '__getitem__'):
                val = row_data[col_name] if col_name in row_data.index else default
            else:
                return default

            if val is None or (isinstance(val, float) and math.isnan(val)):
                return default
            return val
        except (KeyError, IndexError, AttributeError):
            return default

    @classmethod
    def extract_cycle_points(cls, row_data, circuit='LH'):
        """
        Extract all cycle state points from row data for a specific circuit.

        Args:
            row_data: Pandas Series with calculation results
            circuit: 'LH', 'CTR', or 'RH'

        Returns:
            dict: Cycle points with P, h, T, SH/SC data
        """
        circuit_upper = circuit.upper()
        circuit_lower = circuit.lower()

        # Common pressures
        p_suction = cls.safe_get(row_data, 'P_suction')
        p_disch = cls.safe_get(row_data, 'P_disch')

        # Helper to get enthalpy with fallback to multiple column name formats
        def get_enthalpy_with_fallback(old_name, new_name):
            """Try new column name first, fallback to old name."""
            h_val = cls.safe_get(row_data, new_name)
            if h_val is not None:
                return h_val, new_name
            h_val = cls.safe_get(row_data, old_name)
            if h_val is None:
                # Log warning when enthalpy is missing
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Missing enthalpy: tried '{new_name}' and '{old_name}' - both returned None")
            return h_val, old_name

        # Circuit-specific column names
        if circuit_upper == 'LH':
            t_evap_out = 'T_2a-LH'
            t_sat_evap = 'T_sat.lh'
            sh_evap = 'S.H_lh coil'
            h_evap, _ = get_enthalpy_with_fallback('H_coil lh', 'h_2a_LH')
            t_txv_out = 'T_1a-lh'
            h_txv, _ = get_enthalpy_with_fallback('H_txv.lh', 'h_4b_LH')
            sc_txv = 'S.C-txv.lh'
            t_sat_txv = 'T_sat.txv.lh'
            t_txv_in = 'T_4b-lh'
        elif circuit_upper == 'CTR':
            t_evap_out = 'T_2a-ctr'
            t_sat_evap = 'T_sat.ctr'
            sh_evap = 'S.H_ctr coil'
            h_evap, _ = get_enthalpy_with_fallback('H_coil ctr', 'h_2a_CTR')
            t_txv_out = 'T_1a-ctr'
            h_txv, _ = get_enthalpy_with_fallback('H_txv.ctr', 'h_4b_CTR')
            sc_txv = 'S.C-txv.ctr'
            t_sat_txv = 'T_sat.txv.ctr'
            t_txv_in = 'T_4b-ctr'
        else:  # RH
            t_evap_out = 'T_2a-RH'
            t_sat_evap = 'T_sat.rh'
            sh_evap = 'S.H_rh coil'
            h_evap, _ = get_enthalpy_with_fallback('H_coil rh', 'h_2a_RH')
            t_txv_out = 'T_1a-rh'
            h_txv, _ = get_enthalpy_with_fallback('H_txv.rh', 'h_4b_RH')
            sc_txv = 'S.C-txv.rh'
            t_sat_txv = 'T_sat.txv.rh'
            t_txv_in = 'T_4b-rh'

        # Get compressor inlet enthalpy with fallback
        h_comp_in, _ = get_enthalpy_with_fallback('H_comp.in', 'h_2b')

        # Get compressor outlet enthalpy with fallback
        h_comp_out, _ = get_enthalpy_with_fallback('H_comp.out', 'h_3a')

        # If not found, calculate from T_3a and P_disch
        if h_comp_out is None:
            t_3a = cls.safe_get(row_data, 'T_3a')
            if t_3a is not None and p_disch is not None:
                try:
                    from CoolProp.CoolProp import PropsSI
                    # Convert to SI units
                    t_3a_k = (t_3a + 459.67) * 5.0 / 9.0  # °F to K
                    p_disch_pa = (p_disch + 14.696) * 6894.76  # PSIG to Pa
                    # Calculate enthalpy
                    h_comp_out_j = PropsSI('H', 'T', t_3a_k, 'P', p_disch_pa, 'R290')
                    h_comp_out = h_comp_out_j / 1000  # J/kg to kJ/kg
                except Exception:
                    h_comp_out = None  # Calculation failed

        # Extract data points
        cycle_points = {
            '1_evap_inlet': {
                'name': f'Evap {circuit_upper} Inlet',
                'h': h_txv,
                'p': p_suction,
                't': cls.safe_get(row_data, t_txv_out),
                't_sat': cls.safe_get(row_data, t_sat_txv),
                'sc': cls.safe_get(row_data, sc_txv),
                'sh': None,
            },
            '2_evap_outlet': {
                'name': f'Evap {circuit_upper} Outlet',
                'h': h_evap,
                'p': p_suction,
                't': cls.safe_get(row_data, t_evap_out),
                't_sat': cls.safe_get(row_data, t_sat_evap),
                'sh': cls.safe_get(row_data, sh_evap),
                'sc': None,
            },
            '3_comp_inlet': {
                'name': 'Compressor Inlet',
                'h': h_comp_in,
                'p': cls.safe_get(row_data, 'P_suction'),
                't': cls.safe_get(row_data, 'T_2b'),
                't_sat': cls.safe_get(row_data, 'T_sat.comp.in'),
                'sh': cls.safe_get(row_data, 'S.H_total'),
                'sc': None,
            },
            '4_comp_outlet': {
                'name': 'Compressor Outlet',
                'h': h_comp_out,  # Compressor outlet enthalpy (calculated from T_3a and P_disch)
                'p': p_disch,
                't': cls.safe_get(row_data, 'T_3a'),
                't_sat': None,
                'sh': None,  # High superheat vapor
                'sc': None,
            },
            '5_cond_outlet': {
                'name': 'Condenser Outlet',
                'h': h_txv,  # Same as TXV inlet
                'p': p_disch,
                't': cls.safe_get(row_data, 'T_4a'),
                't_sat': cls.safe_get(row_data, 'T_sat.cond'),
                'sh': None,
                'sc': cls.safe_get(row_data, 'S.C'),
            },
            '6_txv_outlet': {
                'name': f'TXV {circuit_upper} Outlet',
                'h': h_txv,
                'p': p_suction,
                't': cls.safe_get(row_data, t_txv_in),
                't_sat': cls.safe_get(row_data, t_sat_txv),
                'sc': cls.safe_get(row_data, sc_txv),
                'sh': None,
            },
        }

        return cycle_points

    @staticmethod
    def classify_state(sh=None, sc=None):
        """
        Classify thermodynamic state based on superheat or subcooling.

        Returns:
            tuple: (label, color, severity)
        """
        if sh is not None:  # Vapor region
            if sh < 0:
                return ("⚠ WET VAPOR", "red", "CRITICAL")
            elif sh < 5:
                return ("⚠ Low SH", "yellow", "WARNING")
            else:
                return ("✓ Healthy", "green", "OK")

        if sc is not None:  # Liquid region
            if sc < 0:
                return ("⚠ FLASH GAS", "orange", "CRITICAL")
            elif sc < 3:
                return ("⚠ Low SC", "yellow", "WARNING")
            else:
                return ("✓ Healthy", "blue", "OK")

        return ("Unknown", "gray", "UNKNOWN")

    @classmethod
    def check_state_health(cls, cycle_points):
        """
        Analyze cycle for abnormal states.

        Returns:
            list: List of warning dictionaries
        """
        warnings = []

        for point_id, data in cycle_points.items():
            sh = data.get('sh')
            sc = data.get('sc')
            point_name = data.get('name', point_id)

            if sh is not None and sh < 0:
                warnings.append({
                    'location': point_name,
                    'issue': 'Wet compression risk',
                    'value': f'SH = {sh:.1f}°F',
                    'severity': 'CRITICAL'
                })
            elif sh is not None and sh < 5:
                warnings.append({
                    'location': point_name,
                    'issue': 'Low superheat',
                    'value': f'SH = {sh:.1f}°F',
                    'severity': 'WARNING'
                })

            if sc is not None and sc < 0:
                warnings.append({
                    'location': point_name,
                    'issue': 'Flash gas present',
                    'value': f'SC = {sc:.1f}°F',
                    'severity': 'CRITICAL'
                })
            elif sc is not None and sc < 3:
                warnings.append({
                    'location': point_name,
                    'issue': 'Low subcooling',
                    'value': f'SC = {sc:.1f}°F',
                    'severity': 'WARNING'
                })

        return warnings

    @classmethod
    def get_summary_text(cls, row_data, circuit='LH'):
        """
        Generate summary text for the selected circuit.

        Returns:
            str: Formatted summary text
        """
        cycle_points = cls.extract_cycle_points(row_data, circuit)
        warnings = cls.check_state_health(cycle_points)

        lines = [f"Circuit: {circuit.upper()}"]
        lines.append("-" * 40)

        # Add key values
        m_dot = cls.safe_get(row_data, 'm_dot')
        qc = cls.safe_get(row_data, 'qc')

        if m_dot is not None:
            lines.append(f"Mass Flow: {m_dot:.2f} lb/hr")
        if qc is not None:
            lines.append(f"Capacity: {qc:.2f} BTU/hr")

        lines.append("")

        # Add warnings if any
        if warnings:
            lines.append("⚠ WARNINGS:")
            for w in warnings:
                lines.append(f"  • {w['location']}: {w['issue']} ({w['value']})")
        else:
            lines.append("✓ All states healthy")

        return "\n".join(lines)
