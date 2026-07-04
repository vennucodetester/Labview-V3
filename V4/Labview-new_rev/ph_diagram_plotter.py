"""
P-h Diagram Plotter for R290 Refrigerant Cycles

Generates P-h (pressure-enthalpy) diagrams with support for multi-circuit overlays.
Uses CoolProp for thermodynamic properties and Matplotlib for visualization.
"""

import numpy as np
import matplotlib.pyplot as plt
from CoolProp.CoolProp import PropsSI
from matplotlib.patches import Rectangle
import warnings
warnings.filterwarnings('ignore')


class PhDiagramPlotter:
    """Generates P-h diagrams for R290 with circuit-specific overlays."""
    
    def __init__(self, refrigerant='R290'):
        self.refrigerant = refrigerant
        self.T_crit = PropsSI('Tcrit', refrigerant)  # Critical temperature [K]
        self.P_crit = PropsSI('Pcrit', refrigerant)  # Critical pressure [Pa]
        
        # Color scheme for circuits
        self.circuit_colors = {
            'LH': '#FF6B6B',    # Red
            'CTR': '#4ECDC4',   # Teal
            'RH': '#45B7D1'     # Blue
        }
        
        self.cycle_color = '#2C3E50'  # Dark gray for main cycle
    
    def get_saturation_line(self, P_min=0.05e6, P_max=4.0e6, num_points=100):
        """
        Calculate saturation line (two-phase boundary) for the refrigerant.
        
        Args:
            P_min: Minimum pressure [Pa]
            P_max: Maximum pressure [Pa]
            num_points: Number of points along the line
            
        Returns:
            h_sat_liquid, h_sat_vapor, P_sat arrays
        """
        pressures = np.logspace(np.log10(P_min), np.log10(P_max), num_points)
        h_f = []  # Saturated liquid enthalpy
        h_g = []  # Saturated vapor enthalpy
        
        for P in pressures:
            try:
                h_f_val = PropsSI('H', 'P', P, 'Q', 0, self.refrigerant) / 1000  # Convert to kJ/kg
                h_g_val = PropsSI('H', 'P', P, 'Q', 1, self.refrigerant) / 1000
                h_f.append(h_f_val)
                h_g.append(h_g_val)
            except:
                pass
        
        return np.array(h_f), np.array(h_g), pressures  # Return pressure in Pa
    
    def get_isotherm_line(self, T, P_min=0.05e6, P_max=4.0e6, num_points=50):
        """
        Calculate an isotherm (constant temperature) line.
        
        Args:
            T: Temperature [K]
            P_min: Minimum pressure [Pa]
            P_max: Maximum pressure [Pa]
            num_points: Number of points along the line
            
        Returns:
            h array, P array
        """
        pressures = np.linspace(P_min, P_max, num_points)
        h_values = []
        valid_pressures = []
        
        for P in pressures:
            try:
                h = PropsSI('H', 'T', T, 'P', P, self.refrigerant) / 1000
                h_values.append(h)
                valid_pressures.append(P)
            except:
                pass
        
        return np.array(h_values), np.array(valid_pressures)  # Return pressure in Pa
    
    def get_isentrope_line(self, S, P_min=0.05e6, P_max=4.0e6, num_points=50):
        """
        Calculate an isentrope (constant entropy) line.
        
        Args:
            S: Entropy [J/(kg·K)]
            P_min: Minimum pressure [Pa]
            P_max: Maximum pressure [Pa]
            num_points: Number of points along the line
            
        Returns:
            h array, P array
        """
        pressures = np.linspace(P_min, P_max, num_points)
        h_values = []
        valid_pressures = []
        
        for P in pressures:
            try:
                h = PropsSI('H', 'S', S, 'P', P, self.refrigerant) / 1000
                h_values.append(h)
                valid_pressures.append(P)
            except:
                pass
        
        return np.array(h_values), np.array(valid_pressures)  # Return pressure in Pa
    
    def plot_ph_diagrams(self, common_points=None, circuit_points=None, 
                        show_LH=True, show_CTR=True, show_RH=True,
                        show_isotherms=True, show_isentropes=True,
                        figsize=(16, 10)):
        """
        Generate P-h diagram with optional circuit-specific cycle overlays.
        
        Args:
            common_points: Dict with common state points {name: {'h': value, 'P': value}}
                          Common states (e.g., 2b suction, 3a discharge)
            
            circuit_points: Dict with circuit-specific states {circuit: {name: {'h': value, 'P': value}}}
                           Example: {'LH': {'2a': {'h': 400, 'P': 1.5}}, ...}
            
            show_LH, show_CTR, show_RH: Boolean toggles to show each circuit
            
            show_isotherms: Draw constant temperature lines
            
            show_isentropes: Draw constant entropy lines
            
            figsize: Tuple (width, height) in inches
            
        Returns:
            fig, ax matplotlib objects
        """
        # Initialize
        common_points = common_points or {}
        circuit_points = circuit_points or {}
        
        # Create figure and axis
        fig, ax = plt.subplots(figsize=figsize)
        fig.patch.set_facecolor('white')
        ax.set_facecolor('#F8F9FA')
        
        # ==================== Plot Saturation Line ====================
        h_f, h_g, P_sat = self.get_saturation_line()
        
        # Two-phase region (between liquid and vapor saturation curves)
        ax.fill_betweenx(P_sat, h_f, h_g, alpha=0.1, color='gray', label='Two-phase region')
        ax.plot(h_f, P_sat, 'k-', linewidth=2, label='Saturated liquid (Q=0)')
        ax.plot(h_g, P_sat, 'k-', linewidth=2, label='Saturated vapor (Q=1)')
        
        # ==================== Plot Background Lines ====================
        if show_isotherms:
            # Plot isotherms (constant temperature lines)
            temperatures = [250, 270, 290, 310, 330, 350]  # K
            for T in temperatures:
                try:
                    h_iso, P_iso = self.get_isotherm_line(T)
                    if len(h_iso) > 1:
                        ax.plot(h_iso, P_iso, 'b--', alpha=0.3, linewidth=0.8)
                        # Add label at a reasonable position
                        mid_idx = len(h_iso) // 2
                        ax.text(h_iso[mid_idx], P_iso[mid_idx], f'{T-273.15:.0f}°C', 
                               fontsize=8, color='blue', alpha=0.6, rotation=0)
                except:
                    pass
        
        if show_isentropes:
            # Plot isentropes (constant entropy lines)
            # Sample a few entropy values from saturation curve
            try:
                P_test = 1.5e6  # Test pressure
                s_values = []
                for Q in np.linspace(0, 1, 5):
                    s = PropsSI('S', 'P', P_test, 'Q', Q, self.refrigerant) / 1000
                    s_values.append(s)
                
                for s in s_values[1:-1]:  # Skip extremes
                    try:
                        h_isen, P_isen = self.get_isentrope_line(s * 1000)  # Convert back to J/(kg·K)
                        if len(h_isen) > 1:
                            ax.plot(h_isen, P_isen, 'g--', alpha=0.2, linewidth=0.8)
                    except:
                        pass
            except:
                pass
        
        # ==================== Plot Common State Points ====================
        if common_points:
            for point_name, point_data in common_points.items():
                h = point_data.get('h')
                P = point_data.get('P')
                if h is not None and P is not None:
                    ax.plot(h, P, 'o', color=self.cycle_color, markersize=8, zorder=10)
                    ax.text(h, P, f'  {point_name}', fontsize=9, fontweight='bold', 
                           verticalalignment='center', color=self.cycle_color)
        
        # ==================== Plot Circuit-Specific Points & Cycles ====================
        active_circuits = []
        if show_LH and 'LH' in circuit_points:
            active_circuits.append('LH')
        if show_CTR and 'CTR' in circuit_points:
            active_circuits.append('CTR')
        if show_RH and 'RH' in circuit_points:
            active_circuits.append('RH')
        
        for circuit in active_circuits:
            points = circuit_points[circuit]
            color = self.circuit_colors[circuit]
            
            # Plot state points for this circuit
            for point_name, point_data in points.items():
                h = point_data.get('h')
                P = point_data.get('P')
                if h is not None and P is not None:
                    ax.plot(h, P, 'o', color=color, markersize=8, zorder=10)
                    ax.text(h, P, f'  {circuit}-{point_name}', fontsize=8, 
                           verticalalignment='center', color=color, alpha=0.8)
            
            # Draw cycle path (connect points in order: 2a -> 2b -> 3a -> 3b -> 4a -> 4b -> 2a)
            cycle_order = ['2a', '2b', '3a', '3b', '4a', '4b']
            h_cycle = []
            P_cycle = []
            
            for point_name in cycle_order:
                if point_name in points:
                    h_cycle.append(points[point_name]['h'])
                    P_cycle.append(points[point_name]['P'])
            
            # Close the cycle
            if h_cycle and len(h_cycle) > 1:
                h_cycle.append(h_cycle[0])
                P_cycle.append(P_cycle[0])
                ax.plot(h_cycle, P_cycle, '-', color=color, linewidth=2.5, 
                       label=f'{circuit} Circuit', zorder=9, alpha=0.8)
        
        # ==================== Formatting ====================
        ax.set_xlabel('Enthalpy [kJ/kg]', fontsize=12, fontweight='bold')
        ax.set_ylabel('Pressure [Pa]', fontsize=12, fontweight='bold')
        ax.set_title(f'P-h Diagram for {self.refrigerant}', fontsize=14, fontweight='bold', pad=20)
        
        # Set limits (in Pa)
        ax.set_xlim(250, 550)
        ax.set_ylim(0.05e5, 4.5e6)
        ax.set_yscale('log')
        
        # Grid
        ax.grid(True, which='both', alpha=0.3, linestyle='-', linewidth=0.5)
        ax.grid(True, which='minor', alpha=0.1, linestyle=':', linewidth=0.3)
        
        # Legend
        handles, labels = ax.get_legend_handles_labels()
        ax.legend(handles, labels, loc='best', fontsize=10, framealpha=0.95)
        
        plt.tight_layout()
        return fig, ax
    
    @staticmethod
    def convert_diagram_model_to_points(filtered_df, circuit_enabled='all'):
        """
        Convert calculated data from the NEW unified calculation system into format for plot_ph_diagrams.

        This function now reads from the DataFrame produced by run_batch_processing() in calculation_orchestrator.py,
        which uses the unified column naming scheme from goal.md.

        Args:
            filtered_df: DataFrame with calculated columns from run_batch_processing()
                        Expected columns:
                        - 'Press.suc', 'Press disch' (pressures in psig)
                        - 'Enthalpy' (compressor inlet, kJ/kg)
                        - 'H_coil lh', 'H_coil ctr', 'H_coil rh' (evaporator outlets, kJ/kg)
                        - 'Enthalpy_txv_lh', 'Enthalpy_txv_ctr', 'Enthalpy_txv_rh' (TXV inlets, kJ/kg)
            circuit_enabled: 'LH', 'CTR', 'RH', or 'all' for all circuits

        Returns:
            common_points, circuit_points dicts
            Format:
            - common_points: {'2b': {'h': value, 'P': value}, ...}
            - circuit_points: {'LH': {'2a': {'h': value, 'P': value}, '4b': {...}}, ...}
        """
        if filtered_df.empty:
            return {}, {}

        # Get the first row (most recent data point) as representative
        data_row = filtered_df.iloc[0]

        # Helper function to convert psig to Pa
        def psig_to_pa(psig):
            """Convert psig to Pa (Pascals)."""
            if psig is None:
                return None
            psi_abs = psig + 14.696  # Convert to absolute pressure
            pa = psi_abs * 6894.76  # Convert to Pascals
            return pa

        # Extract pressures and convert to Pa
        P_suc_psig = data_row.get('Press.suc')
        P_disch_psig = data_row.get('Press disch')

        P_suc_pa = psig_to_pa(P_suc_psig) if P_suc_psig is not None else None
        P_disch_pa = psig_to_pa(P_disch_psig) if P_disch_psig is not None else None

        # Common state points
        common_points = {}

        # State 2b: Compressor inlet (mixed average of three evaporator outlets)
        h_2b = data_row.get('Enthalpy')  # This is from "At compressor inlet" group
        if h_2b is not None and P_suc_pa is not None:
            common_points['2b'] = {'h': h_2b, 'P': P_suc_pa}

        # Circuit-specific state points
        circuit_points = {'LH': {}, 'CTR': {}, 'RH': {}}

        # Map circuit names to DataFrame column suffixes
        circuit_col_map = {
            'LH': 'lh',
            'CTR': 'ctr',
            'RH': 'rh'
        }

        for circuit, col_suffix in circuit_col_map.items():
            # State 2a: Evaporator outlet (superheat point on low-pressure line)
            h_2a = data_row.get(f'H_coil {col_suffix}')
            if h_2a is not None and P_suc_pa is not None:
                circuit_points[circuit]['2a'] = {'h': h_2a, 'P': P_suc_pa}

            # State 4b: TXV inlet (subcooling point on high-pressure line)
            h_4b = data_row.get(f'Enthalpy_txv_{col_suffix}')
            if h_4b is not None and P_disch_pa is not None:
                circuit_points[circuit]['4b'] = {'h': h_4b, 'P': P_disch_pa}

        return common_points, circuit_points


# Example usage function
def plot_example_ph_diagram():
    """Create an example P-h diagram with sample data."""
    plotter = PhDiagramPlotter('R290')
    
    # Sample common points (pressures in Pa)
    common_points = {
        '2b': {'h': 410.5, 'P': 1.825e6},
        '3a': {'h': 473.2, 'P': 2.856e6},
        '3b': {'h': 450.0, 'P': 2.856e6},
    }
    
    # Sample circuit-specific points (pressures in Pa)
    circuit_points = {
        'LH': {
            '2a': {'h': 420.0, 'P': 1.825e6},
            '4b': {'h': 290.0, 'P': 2.856e6},
        },
        'CTR': {
            '2a': {'h': 418.0, 'P': 1.825e6},
            '4b': {'h': 288.0, 'P': 2.856e6},
        },
        'RH': {
            '2a': {'h': 422.0, 'P': 1.825e6},
            '4b': {'h': 292.0, 'P': 2.856e6},
        }
    }
    
    fig, ax = plotter.plot_ph_diagrams(
        common_points=common_points,
        circuit_points=circuit_points,
        show_LH=True,
        show_CTR=True,
        show_RH=True,
        show_isotherms=True,
        show_isentropes=True
    )
    
    plt.show()
    return fig, ax
