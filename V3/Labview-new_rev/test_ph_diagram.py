"""Quick test for P-h diagram functionality"""

from ph_diagram_plotter import PhDiagramPlotter

print('[TEST] Initializing PhDiagramPlotter...')
p = PhDiagramPlotter('R290')
print('[TEST] ✓ PhDiagramPlotter initialized successfully')

print('[TEST] Computing saturation line...')
h_f, h_g, P_sat = p.get_saturation_line()
print(f'[TEST] ✓ Saturation line: {len(h_f)} points, P range {P_sat.min():.3f}-{P_sat.max():.3f} MPa')

print('[TEST] Computing isotherm line...')
h_iso, P_iso = p.get_isotherm_line(300)  # 300K
print(f'[TEST] ✓ Isotherm (300K): {len(h_iso)} points')

print('[TEST] Computing isentrope line...')
h_isen, P_isen = p.get_isentrope_line(1700)  # J/(kg·K)
print(f'[TEST] ✓ Isentrope: {len(h_isen)} points')

print('\n[TEST] All P-h diagram tests passed! ✓')
